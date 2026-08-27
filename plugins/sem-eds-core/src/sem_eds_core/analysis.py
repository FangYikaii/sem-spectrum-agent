"""Deterministic, screening-grade EDS background and peak-fitting engine.

This module is intentionally conservative. It provides auditable intermediate
arrays and refuses to label its normalized peak areas as concentrations.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np

from .lines import CATALOG_ID, CATALOG_VERSION, lines_for_elements, supported_elements
from .models import (
    EdsSpectrum,
    FitRequest,
    FitResponse,
    FitResult,
    LineDefinition,
    PeakFit,
    Provenance,
    QuantificationResult,
    RelativeElement,
    SolverDiagnostics,
    ValidationIssue,
    ValidationReport,
)
from .validation import validate_spectrum


MN_KA_EV = 5898.75
GAUSSIAN_FWHM_TO_SIGMA = 2.354820045
MIN_ACCEPTED_SNR = 3.0


class SpectrumQualityError(ValueError):
    def __init__(self, report: ValidationReport) -> None:
        super().__init__("Spectrum failed mandatory quality gates.")
        self.report = report


class UnsupportedElementError(ValueError):
    pass


class NoUsableLinesError(ValueError):
    pass


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _spectrum_hash(spectrum: EdsSpectrum) -> str:
    return _sha256_json(spectrum.model_dump(mode="json"))


def snip_background(counts: np.ndarray, iterations: int) -> np.ndarray:
    """Compute a simple log-space SNIP-like background approximation.

    The implementation is a deterministic approximation intended for reference
    tests. It is not a calibrated detector-background model.
    """

    transformed = np.log1p(np.clip(counts.astype(float), 0.0, None))
    clipped = transformed.copy()
    n = clipped.size
    for width in range(1, min(iterations, max((n - 1) // 2, 1)) + 1):
        if 2 * width >= n:
            break
        local_average = 0.5 * (clipped[:-2 * width] + clipped[2 * width :])
        current = clipped[width:-width]
        clipped[width:-width] = np.minimum(current, local_average)
    return np.expm1(clipped)


def _fwhm_at_energy(energy_ev: float, spectrum: EdsSpectrum, request: FitRequest) -> float:
    reference_fwhm = spectrum.metadata.detector_fwhm_ev_at_mn_ka or request.settings.fwhm_ev_at_mn_ka
    return float(reference_fwhm * np.sqrt(max(energy_ev, 1.0) / MN_KA_EV))


def _unit_area_gaussian(energy: np.ndarray, centre_ev: float, fwhm_ev: float) -> np.ndarray:
    sigma = max(fwhm_ev / GAUSSIAN_FWHM_TO_SIGMA, 1e-9)
    profile = np.exp(-0.5 * ((energy - centre_ev) / sigma) ** 2)
    area = float(np.trapezoid(profile, energy))
    if area <= 0 or not np.isfinite(area):
        raise NoUsableLinesError("A candidate line cannot be represented on the supplied energy axis.")
    return profile / area


def _projected_gradient_nnls(
    matrix: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[np.ndarray, SolverDiagnostics]:
    """Solve weighted non-negative least squares without a SciPy dependency."""

    weighted_matrix = matrix * weights[:, np.newaxis]
    weighted_target = target * weights
    gram = weighted_matrix.T @ weighted_matrix
    rhs = weighted_matrix.T @ weighted_target
    eigenvalues = np.linalg.eigvalsh(gram)
    lipschitz = float(np.max(eigenvalues)) if eigenvalues.size else 0.0
    if lipschitz <= 0 or not np.isfinite(lipschitz):
        coefficients = np.zeros(matrix.shape[1], dtype=float)
        return coefficients, SolverDiagnostics(iterations=0, converged=True, objective=0.0)

    step = 1.0 / lipschitz
    coefficients = np.zeros(matrix.shape[1], dtype=float)
    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        next_coefficients = np.maximum(coefficients - step * (gram @ coefficients - rhs), 0.0)
        delta = float(np.linalg.norm(next_coefficients - coefficients))
        scale = 1.0 + float(np.linalg.norm(coefficients))
        coefficients = next_coefficients
        if delta <= tolerance * scale:
            converged = True
            break

    residual = weighted_matrix @ coefficients - weighted_target
    objective = float(0.5 * np.dot(residual, residual))
    return coefficients, SolverDiagnostics(
        iterations=iterations,
        converged=converged,
        objective=max(objective, 0.0),
    )


def _usable_lines(request: FitRequest, validation: ValidationReport) -> list[LineDefinition]:
    unknown = sorted(set(request.candidate_elements) - supported_elements())
    if unknown:
        raise UnsupportedElementError(f"Unsupported candidate elements: {', '.join(unknown)}")

    energy = np.asarray(request.spectrum.energy_ev, dtype=float)
    lower, upper = float(np.min(energy)), float(np.max(energy))
    usable: list[LineDefinition] = []
    for line in lines_for_elements(request.candidate_elements):
        if not lower <= line.energy_ev <= upper:
            validation.warnings.append(
                ValidationIssue(
                    code="candidate_line_out_of_range",
                    message=f"{line.element} {line.line} at {line.energy_ev:.2f} eV is outside the spectrum range.",
                    field="candidate_elements",
                )
            )
            continue
        if request.spectrum.metadata.beam_kv and line.energy_ev >= request.spectrum.metadata.beam_kv * 1000.0:
            validation.warnings.append(
                ValidationIssue(
                    code="candidate_line_at_or_above_beam_energy",
                    message=(
                        f"{line.element} {line.line} line energy {line.energy_ev:.2f} eV is at or above "
                        f"the declared beam energy {request.spectrum.metadata.beam_kv * 1000.0:.2f} eV."
                    ),
                    field="candidate_elements",
                )
            )
            continue
        usable.append(line)
    if not usable:
        raise NoUsableLinesError("No candidate lines are within the usable energy range.")
    return usable


def _provenance(request: FitRequest) -> Provenance:
    parameter_payload = {
        "candidate_elements": request.candidate_elements,
        "settings": request.settings.model_dump(mode="json"),
        "catalog_id": CATALOG_ID,
        "catalog_version": CATALOG_VERSION,
        "algorithm": "snip-log-v1+projected-gradient-nnls",
    }
    calibration = request.spectrum.calibration
    return Provenance(
        plugin_version="0.1.0",
        input_asset_id=request.spectrum.asset_id,
        input_sha256=_spectrum_hash(request.spectrum),
        calibration_id=calibration.calibration_id if calibration else None,
        calibration_revision=calibration.revision if calibration else None,
        analysis_parameters_sha256=_sha256_json(parameter_payload),
        created_at=datetime.now(timezone.utc),
    )


def fit_spectrum(request: FitRequest) -> FitResponse:
    """Validate then fit selected demonstration reference lines to a spectrum."""

    validation = validate_spectrum(request.spectrum, request.settings)
    if not validation.valid:
        raise SpectrumQualityError(validation)

    lines = _usable_lines(request, validation)
    energy = np.asarray(request.spectrum.energy_ev, dtype=float)
    counts = np.asarray(request.spectrum.counts, dtype=float)
    background = snip_background(counts, request.settings.background_iterations)
    net_counts = np.clip(counts - background, 0.0, None)

    fwhms = np.asarray([_fwhm_at_energy(line.energy_ev, request.spectrum, request) for line in lines])
    matrix = np.column_stack(
        [_unit_area_gaussian(energy, line.energy_ev, fwhm) for line, fwhm in zip(lines, fwhms, strict=True)]
    )
    weights = 1.0 / np.sqrt(np.maximum(counts, 1.0))
    coefficients, solver = _projected_gradient_nnls(
        matrix,
        net_counts,
        weights,
        max_iterations=request.settings.max_solver_iterations,
        tolerance=request.settings.solver_tolerance,
    )
    peak_model = matrix @ coefficients
    full_model = background + peak_model
    residual = counts - full_model

    peaks: list[PeakFit] = []
    for index, (line, fwhm, coefficient) in enumerate(zip(lines, fwhms, coefficients, strict=True)):
        local_mask = np.abs(energy - line.energy_ev) <= max(2.0 * fwhm, 1.0)
        local_observed = float(np.sum(counts[local_mask]))
        snr = float(coefficient / np.sqrt(max(local_observed, 1.0)))
        accepted = bool(coefficient >= request.settings.min_peak_area and snr >= MIN_ACCEPTED_SNR)
        rejection_reason: str | None = None
        if not accepted:
            reasons: list[str] = []
            if coefficient < request.settings.min_peak_area:
                reasons.append("below_min_peak_area")
            if snr < MIN_ACCEPTED_SNR:
                reasons.append("below_minimum_snr")
            rejection_reason = ",".join(reasons)
        peaks.append(
            PeakFit(
                element=line.element,
                line=line.line,
                energy_ev=line.energy_ev,
                fwhm_ev=float(fwhm),
                net_area=float(max(coefficient, 0.0)),
                snr=max(snr, 0.0),
                accepted=accepted,
                rejection_reason=rejection_reason,
            )
        )

    degrees_of_freedom = max(len(counts) - len(coefficients), 1)
    chi_square = float(np.sum((residual**2) / np.maximum(full_model, 1.0)) / degrees_of_freedom)
    resolution_fwhm = request.spectrum.metadata.detector_fwhm_ev_at_mn_ka or request.settings.fwhm_ev_at_mn_ka
    fit = FitResult(
        catalog_id=CATALOG_ID,
        catalog_version=CATALOG_VERSION,
        resolution_model=f"fwhm(E)={resolution_fwhm:.3f}*sqrt(max(E,1)/{MN_KA_EV:.2f})",
        peaks=peaks,
        model_counts=full_model.tolist(),
        background_counts=background.tolist(),
        residual_counts=residual.tolist(),
        reduced_chi_square=max(chi_square, 0.0),
        solver=solver,
    )
    return FitResponse(validation=validation, fit=fit, provenance=_provenance(request))


def quantify_spectrum(request: FitRequest) -> QuantificationResult:
    """Return explicitly non-concentration relative intensities from accepted peaks."""

    fit_response = fit_spectrum(request)
    element_areas: dict[str, float] = {}
    for peak in fit_response.fit.peaks:
        if peak.accepted:
            element_areas[peak.element] = element_areas.get(peak.element, 0.0) + peak.net_area
    total_area = float(sum(element_areas.values()))
    if total_area <= 0:
        raise NoUsableLinesError("No accepted peak has sufficient screening-grade net area.")

    elements = [
        RelativeElement(element=element, net_area=area, relative_fraction=area / total_area)
        for element, area in sorted(element_areas.items())
    ]
    return QuantificationResult(
        elements=elements,
        disclaimer=(
            "Not a standard-corrected EDS concentration; do not interpret as wt% or at%. "
            "Values are normalized net peak areas from the selected demo line catalog."
        ),
        validation=fit_response.validation,
        provenance=fit_response.provenance,
    )

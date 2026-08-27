"""Quality gates for screening-grade EDS spectra."""

from __future__ import annotations

import numpy as np

from .models import EdsSpectrum, FitSettings, ValidationIssue, ValidationReport


MIN_CHANNELS = 64
MIN_RANGE_EV = 1000.0
IRREGULAR_SPACING_CV = 0.01


def _issue(code: str, message: str, field: str | None = None) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, field=field)


def validate_spectrum(spectrum: EdsSpectrum, settings: FitSettings) -> ValidationReport:
    """Apply deterministic pre-flight checks without mutating the input spectrum."""

    energy = np.asarray(spectrum.energy_ev, dtype=float)
    counts = np.asarray(spectrum.counts, dtype=float)
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    flags = ["SCREENING_ONLY"]

    if energy.size < MIN_CHANNELS:
        errors.append(
            _issue(
                "insufficient_channels",
                f"EDS fitting requires at least {MIN_CHANNELS} channels; received {energy.size}.",
                "energy_ev",
            )
        )

    if not np.isfinite(energy).all():
        errors.append(_issue("invalid_energy_axis", "Energy values must be finite.", "energy_ev"))
    if not np.isfinite(counts).all():
        errors.append(_issue("invalid_counts", "Counts must be finite.", "counts"))
    if np.any(counts < 0):
        errors.append(_issue("negative_counts", "Counts must not be negative.", "counts"))

    spacing = np.diff(energy)
    if spacing.size and np.any(spacing <= 0):
        errors.append(
            _issue(
                "non_monotonic_energy_axis",
                "energy_ev must be strictly increasing.",
                "energy_ev",
            )
        )

    if spectrum.metadata.real_time_s is not None and spectrum.metadata.live_time_s is not None:
        if spectrum.metadata.real_time_s < spectrum.metadata.live_time_s:
            errors.append(
                _issue(
                    "real_time_less_than_live_time",
                    "real_time_s must be greater than or equal to live_time_s.",
                    "metadata.real_time_s",
                )
            )

    calibration_is_verified = bool(spectrum.calibration and spectrum.calibration.is_verified)
    if settings.require_verified_calibration and not calibration_is_verified:
        errors.append(
            _issue(
                "missing_verified_calibration",
                "This request requires calibration_id and revision.",
                "calibration",
            )
        )
    elif not calibration_is_verified:
        warnings.append(
            _issue(
                "missing_verified_calibration",
                "No verified calibration was supplied; result is screening-only.",
                "calibration",
            )
        )
        flags.append("UNCALIBRATED_INPUT")

    if spectrum.metadata.live_time_s is None:
        warnings.append(
            _issue(
                "missing_live_time",
                "live_time_s is absent; rate-normalized comparison is not supported.",
                "metadata.live_time_s",
            )
        )
    if spectrum.metadata.beam_kv is None:
        warnings.append(
            _issue(
                "missing_beam_energy",
                "beam_kv is absent; line-excitation plausibility is not checked.",
                "metadata.beam_kv",
            )
        )
    if spectrum.metadata.detector_fwhm_ev_at_mn_ka is None:
        warnings.append(
            _issue(
                "missing_detector_resolution",
                "No detector FWHM supplied; request default is used for the response model.",
                "metadata.detector_fwhm_ev_at_mn_ka",
            )
        )

    if spectrum.metadata.signal_type and spectrum.metadata.signal_type.upper() not in {"EDS", "XEDS"}:
        warnings.append(
            _issue(
                "unexpected_signal_type",
                f"signal_type={spectrum.metadata.signal_type!r} is not recognised as EDS/XEDS.",
                "metadata.signal_type",
            )
        )

    total_counts = float(np.sum(counts)) if counts.size else 0.0
    if total_counts < settings.min_total_counts:
        warnings.append(
            _issue(
                "low_total_counts",
                f"Total counts {total_counts:.3f} are below configured threshold {settings.min_total_counts:.3f}.",
                "counts",
            )
        )
        flags.append("LOW_COUNTS")

    energy_min = float(np.min(energy)) if energy.size else 0.0
    energy_max = float(np.max(energy)) if energy.size else 0.0
    energy_range = energy_max - energy_min
    if energy.size > 1 and energy_range < MIN_RANGE_EV:
        warnings.append(
            _issue(
                "limited_energy_range",
                f"Energy range is {energy_range:.3f} eV; interpretation is limited below {MIN_RANGE_EV:.0f} eV.",
                "energy_ev",
            )
        )

    spacing_cv = 0.0
    if spacing.size and np.all(spacing > 0):
        mean_spacing = float(np.mean(spacing))
        spacing_cv = float(np.std(spacing) / mean_spacing) if mean_spacing else 0.0
        if spacing_cv > IRREGULAR_SPACING_CV:
            warnings.append(
                _issue(
                    "irregular_channel_spacing",
                    f"Channel spacing coefficient of variation is {spacing_cv:.5f}, above {IRREGULAR_SPACING_CV:.5f}.",
                    "energy_ev",
                )
            )

    metrics: dict[str, float | int | str] = {
        "channels": int(energy.size),
        "total_counts": total_counts,
        "energy_min_ev": energy_min,
        "energy_max_ev": energy_max,
        "energy_range_ev": energy_range,
        "mean_channel_spacing_ev": float(np.mean(spacing)) if spacing.size else 0.0,
        "channel_spacing_cv": spacing_cv,
    }
    return ValidationReport(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        metrics=metrics,
        quality_flags=flags,
    )

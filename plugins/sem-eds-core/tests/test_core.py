from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from sem_eds_core.analysis import fit_spectrum, quantify_spectrum
from sem_eds_core.emsa import parse_emsa_text
from sem_eds_core.models import CalibrationRef, EdsSpectrum, FitRequest, FitSettings, SpectrumMetadata
from sem_eds_core.server import app
from sem_eds_core.validation import validate_spectrum


def _gaussian(energy: np.ndarray, centre_ev: float, fwhm_ev: float, area: float) -> np.ndarray:
    sigma = fwhm_ev / 2.354820045
    profile = np.exp(-0.5 * ((energy - centre_ev) / sigma) ** 2)
    return area * profile / np.trapezoid(profile, energy)


def synthetic_spectrum() -> EdsSpectrum:
    energy = np.arange(0.0, 10240.0, 10.0)
    counts = 18.0 + 0.003 * energy
    counts += _gaussian(energy, 524.9, 105.0, 6_000.0)
    counts += _gaussian(energy, 1486.7, 120.0, 3_000.0)
    counts += _gaussian(energy, 1739.98, 125.0, 18_000.0)
    counts = np.clip(counts, 0.0, None)
    return EdsSpectrum(
        case_id="case_test_001",
        asset_id="sha256:test-fixture",
        energy_ev=energy.tolist(),
        counts=counts.tolist(),
        metadata=SpectrumMetadata(
            signal_type="EDS",
            live_time_s=60.0,
            real_time_s=72.0,
            beam_kv=10.0,
            detector_id="synthetic-detector",
            detector_fwhm_ev_at_mn_ka=130.0,
            source_format="test",
        ),
        calibration=CalibrationRef(calibration_id="cal-test", revision="1"),
    )


def request_for_synthetic_spectrum() -> FitRequest:
    return FitRequest(
        spectrum=synthetic_spectrum(),
        candidate_elements=["O", "Al", "Si"],
        settings=FitSettings(min_total_counts=1_000.0, min_peak_area=10.0),
    )


def test_emsa_parser_reads_demo_fixture() -> None:
    fixture = Path(__file__).parents[1] / "examples" / "silicon_oxide_demo.emsa"
    response = parse_emsa_text(
        case_id="case_test_001",
        asset_id="sha256:fixture",
        emsa_text=fixture.read_text(encoding="utf-8"),
        calibration=CalibrationRef(calibration_id="cal-test", revision="1"),
    )
    assert len(response.spectrum.energy_ev) == 1024
    assert response.spectrum.energy_ev[0] == 0.0
    assert response.spectrum.energy_ev[-1] == 10230.0
    assert response.spectrum.metadata.live_time_s == 60.0
    assert response.spectrum.metadata.signal_type == "EDS"
    assert not response.warnings


def test_validation_rejects_non_monotonic_axis() -> None:
    spectrum = synthetic_spectrum().model_copy(update={"energy_ev": [1.0] * 64, "counts": [1.0] * 64})
    report = validate_spectrum(spectrum, FitSettings())
    assert not report.valid
    assert "non_monotonic_energy_axis" in {issue.code for issue in report.errors}


def test_fit_identifies_synthetic_si_o_and_al_lines() -> None:
    response = fit_spectrum(request_for_synthetic_spectrum())
    assert response.validation.valid
    peaks = {peak.element: peak for peak in response.fit.peaks}
    assert peaks["Si"].accepted
    assert peaks["O"].accepted
    assert peaks["Al"].accepted
    assert peaks["Si"].net_area > peaks["O"].net_area > peaks["Al"].net_area
    assert response.fit.solver.converged
    assert len(response.fit.residual_counts) == len(response.fit.model_counts) == 1024
    assert response.provenance.input_sha256.startswith("sha256:")


def test_quantification_is_explicitly_screening_only() -> None:
    response = quantify_spectrum(request_for_synthetic_spectrum())
    fractions = {element.element: element.relative_fraction for element in response.elements}
    assert response.screening_only is True
    assert abs(sum(fractions.values()) - 1.0) < 1e-12
    assert fractions["Si"] > fractions["O"] > fractions["Al"]
    assert "wt%" in response.disclaimer


def test_http_fit_and_catalog_endpoints() -> None:
    client = TestClient(app)
    catalog = client.get("/v1/line-catalog")
    assert catalog.status_code == 200
    assert catalog.json()["reference_status"] == "demo_reference_only"

    payload = request_for_synthetic_spectrum().model_dump(mode="json")
    response = client.post("/v1/eds/fit", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["validation"]["valid"] is True
    assert any(peak["element"] == "Si" and peak["accepted"] for peak in body["fit"]["peaks"])


def test_http_quality_failure_is_structured() -> None:
    client = TestClient(app)
    invalid = synthetic_spectrum().model_copy(update={"counts": [-1.0] * 64, "energy_ev": list(range(64))})
    payload = {
        "spectrum": invalid.model_dump(mode="json"),
        "candidate_elements": ["Si"],
        "settings": {"min_total_counts": 0.0},
    }
    response = client.post("/v1/eds/fit", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "spectrum_quality_failed"
    assert {issue["code"] for issue in response.json()["detail"]["issues"]} >= {"negative_counts"}

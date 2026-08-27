"""Pydantic contracts shared by the HTTP API and MCP tools.

The contracts intentionally model screening-grade results. They do not expose
weight-percent or atomic-percent fields because those require a validated
instrument and matrix-correction workflow outside this plugin's scope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Reject unknown fields so contracts cannot silently drift."""

    model_config = ConfigDict(extra="forbid")


class CalibrationRef(StrictModel):
    calibration_id: str | None = Field(default=None, min_length=1, max_length=160)
    revision: str | None = Field(default=None, min_length=1, max_length=80)
    energy_reference: str | None = Field(default=None, max_length=160)
    verified_at: datetime | None = None

    @property
    def is_verified(self) -> bool:
        return bool(self.calibration_id and self.revision)


class SpectrumMetadata(StrictModel):
    signal_type: str | None = Field(default="EDS", max_length=32)
    live_time_s: float | None = Field(default=None, gt=0)
    real_time_s: float | None = Field(default=None, gt=0)
    beam_kv: float | None = Field(default=None, gt=0)
    detector_id: str | None = Field(default=None, max_length=160)
    detector_fwhm_ev_at_mn_ka: float | None = Field(default=None, gt=1, le=1000)
    source_format: str | None = Field(default=None, max_length=80)
    raw_headers: dict[str, str] = Field(default_factory=dict)
    user_headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_acquisition_times(self) -> "SpectrumMetadata":
        if (
            self.live_time_s is not None
            and self.real_time_s is not None
            and self.real_time_s < self.live_time_s
        ):
            raise ValueError("real_time_s must be greater than or equal to live_time_s")
        return self


class EdsSpectrum(StrictModel):
    case_id: str = Field(min_length=3, max_length=160)
    asset_id: str = Field(min_length=3, max_length=320)
    energy_ev: list[float] = Field(min_length=2)
    counts: list[float] = Field(min_length=2)
    metadata: SpectrumMetadata = Field(default_factory=SpectrumMetadata)
    calibration: CalibrationRef | None = None

    @field_validator("energy_ev", "counts")
    @classmethod
    def values_must_be_finite(cls, values: list[float]) -> list[float]:
        for value in values:
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("spectrum values must be finite")
        return values

    @model_validator(mode="after")
    def arrays_must_align(self) -> "EdsSpectrum":
        if len(self.energy_ev) != len(self.counts):
            raise ValueError("energy_ev and counts must have equal lengths")
        return self


class ValidationIssue(StrictModel):
    code: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=3, max_length=500)
    field: str | None = Field(default=None, max_length=120)


class ValidationReport(StrictModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)


class FitSettings(StrictModel):
    background_iterations: int = Field(default=24, ge=4, le=128)
    min_total_counts: float = Field(default=1000.0, ge=0)
    min_peak_area: float = Field(default=25.0, ge=0)
    require_verified_calibration: bool = False
    fwhm_ev_at_mn_ka: float = Field(default=130.0, gt=1, le=1000)
    max_solver_iterations: int = Field(default=2000, ge=50, le=20000)
    solver_tolerance: float = Field(default=1e-6, gt=0, le=0.1)


class ValidateRequest(StrictModel):
    spectrum: EdsSpectrum
    settings: FitSettings = Field(default_factory=FitSettings)


class ParseEmsaRequest(StrictModel):
    case_id: str = Field(min_length=3, max_length=160)
    asset_id: str = Field(min_length=3, max_length=320)
    emsa_text: str = Field(min_length=20, max_length=20_000_000)
    calibration: CalibrationRef | None = None


class ParseEmsaResponse(StrictModel):
    spectrum: EdsSpectrum
    warnings: list[ValidationIssue] = Field(default_factory=list)


class LineDefinition(StrictModel):
    element: str = Field(pattern=r"^[A-Z][a-z]?$", min_length=1, max_length=2)
    line: str = Field(min_length=2, max_length=16)
    energy_ev: float = Field(gt=0)
    family: Literal["K", "L", "M"]
    relative_intensity: float = Field(default=1.0, gt=0)


class LineCatalogResponse(StrictModel):
    catalog_id: str
    catalog_version: str
    reference_status: Literal["demo_reference_only", "validated"]
    lines: list[LineDefinition]


class PeakFit(StrictModel):
    element: str
    line: str
    energy_ev: float
    fwhm_ev: float = Field(gt=0)
    net_area: float = Field(ge=0)
    snr: float = Field(ge=0)
    accepted: bool
    rejection_reason: str | None = None


class SolverDiagnostics(StrictModel):
    name: Literal["projected-gradient-nnls"] = "projected-gradient-nnls"
    iterations: int = Field(ge=0)
    converged: bool
    objective: float = Field(ge=0)


class FitResult(StrictModel):
    catalog_id: str
    catalog_version: str
    background_method: Literal["snip-log-v1"] = "snip-log-v1"
    resolution_model: str
    peaks: list[PeakFit]
    model_counts: list[float]
    background_counts: list[float]
    residual_counts: list[float]
    reduced_chi_square: float | None = Field(default=None, ge=0)
    solver: SolverDiagnostics


class Provenance(StrictModel):
    plugin_id: Literal["com.semispectra.eds-core"] = "com.semispectra.eds-core"
    plugin_version: str
    input_asset_id: str
    input_sha256: str
    calibration_id: str | None = None
    calibration_revision: str | None = None
    analysis_parameters_sha256: str
    created_at: datetime


class FitRequest(StrictModel):
    spectrum: EdsSpectrum
    candidate_elements: list[str] = Field(min_length=1, max_length=32)
    settings: FitSettings = Field(default_factory=FitSettings)

    @field_validator("candidate_elements")
    @classmethod
    def normalise_elements(cls, values: list[str]) -> list[str]:
        normalised = [value.strip().capitalize() for value in values]
        if len(set(normalised)) != len(normalised):
            raise ValueError("candidate_elements must not contain duplicates")
        for value in normalised:
            if not value.isalpha() or len(value) > 2:
                raise ValueError("candidate_elements must contain element symbols")
        return normalised


class FitResponse(StrictModel):
    validation: ValidationReport
    fit: FitResult
    provenance: Provenance


class RelativeElement(StrictModel):
    element: str
    net_area: float = Field(ge=0)
    relative_fraction: float = Field(ge=0, le=1)


class QuantificationResult(StrictModel):
    screening_only: Literal[True] = True
    quantification_method: Literal["normalized-net-peak-area"] = "normalized-net-peak-area"
    elements: list[RelativeElement]
    disclaimer: str
    validation: ValidationReport
    provenance: Provenance


class ErrorDetail(StrictModel):
    code: str
    message: str
    issues: list[ValidationIssue] = Field(default_factory=list)


JsonDict = dict[str, Any]

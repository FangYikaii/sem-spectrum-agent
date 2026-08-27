"""FastAPI surface for the sem-eds-core plugin."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .analysis import NoUsableLinesError, SpectrumQualityError, UnsupportedElementError, fit_spectrum, quantify_spectrum
from .emsa import EmsaParseError, parse_emsa_text
from .lines import catalog_response
from .models import (
    ErrorDetail,
    FitRequest,
    FitResponse,
    LineCatalogResponse,
    ParseEmsaRequest,
    ParseEmsaResponse,
    QuantificationResult,
    ValidateRequest,
    ValidationIssue,
    ValidationReport,
)
from .validation import validate_spectrum

PLUGIN_VERSION = "0.1.0"


def _error_response(status_code: int, code: str, message: str, issues: list[ValidationIssue] | None = None) -> JSONResponse:
    detail = ErrorDetail(code=code, message=message, issues=issues or [])
    return JSONResponse(status_code=status_code, content={"detail": detail.model_dump(mode="json")})


def create_app() -> FastAPI:
    app = FastAPI(
        title="sem-eds-core",
        summary="Auditable, screening-grade SEM-EDS spectrum validation and peak fitting.",
        version=PLUGIN_VERSION,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url=None,
    )

    @app.exception_handler(SpectrumQualityError)
    async def spectrum_quality_error_handler(_: Request, exc: SpectrumQualityError) -> JSONResponse:
        return _error_response(
            422,
            "spectrum_quality_failed",
            "Spectrum failed mandatory quality gates.",
            exc.report.errors,
        )

    @app.exception_handler(UnsupportedElementError)
    async def unsupported_element_handler(_: Request, exc: UnsupportedElementError) -> JSONResponse:
        return _error_response(400, "unsupported_element", str(exc))

    @app.exception_handler(NoUsableLinesError)
    async def no_usable_lines_handler(_: Request, exc: NoUsableLinesError) -> JSONResponse:
        return _error_response(422, "no_accepted_peak_area", str(exc))

    @app.exception_handler(EmsaParseError)
    async def emsa_parse_handler(_: Request, exc: EmsaParseError) -> JSONResponse:
        return _error_response(422, "emsa_parse_failed", str(exc))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [
            ValidationIssue(
                code="request_validation_error",
                message=error["msg"],
                field=".".join(str(part) for part in error.get("loc", [])),
            )
            for error in exc.errors()
        ]
        return _error_response(422, "request_validation_error", "Request does not match the API contract.", issues)

    @app.get("/healthz", tags=["operations"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "plugin_id": "com.semispectra.eds-core", "version": PLUGIN_VERSION}

    @app.get("/v1/line-catalog", response_model=LineCatalogResponse, tags=["reference-data"])
    def line_catalog() -> LineCatalogResponse:
        return catalog_response()

    @app.post("/v1/eds/parse-emsa", response_model=ParseEmsaResponse, tags=["eds"])
    def parse_emsa(request: ParseEmsaRequest) -> ParseEmsaResponse:
        return parse_emsa_text(
            case_id=request.case_id,
            asset_id=request.asset_id,
            emsa_text=request.emsa_text,
            calibration=request.calibration,
        )

    @app.post("/v1/eds/validate", response_model=ValidationReport, tags=["eds"])
    def validate(request: ValidateRequest) -> ValidationReport:
        return validate_spectrum(request.spectrum, request.settings)

    @app.post("/v1/eds/fit", response_model=FitResponse, tags=["eds"])
    def fit(request: FitRequest) -> FitResponse:
        return fit_spectrum(request)

    @app.post("/v1/eds/quantify", response_model=QuantificationResult, tags=["eds"])
    def quantify(request: FitRequest) -> QuantificationResult:
        return quantify_spectrum(request)

    return app


app = create_app()

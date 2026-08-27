"""Optional FastMCP adapter for sem-eds-core.

Install with `pip install -e '.[mcp]'` before using this module. The adapter is
thin by design: HTTP and MCP calls share exactly the same Pydantic contracts
and deterministic analysis implementation.
"""

from __future__ import annotations

from .analysis import fit_spectrum, quantify_spectrum
from .emsa import parse_emsa_text
from .lines import catalog_response
from .models import FitRequest, ParseEmsaRequest, ValidateRequest
from .validation import validate_spectrum


def create_mcp_server():
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("FastMCP is not installed. Install with: pip install -e '.[mcp]'") from exc

    mcp = FastMCP(
        "sem-eds-core",
        instructions=(
            "Screening-grade, read-only SEM-EDS analysis. Results are not concentrations and must be reviewed "
            "with calibration, spectrum quality and provenance before use."
        ),
    )

    @mcp.tool(name="spectra.validate_eds")
    def validate_eds(request: ValidateRequest) -> dict:
        """Apply EDS quality gates without modifying data or interacting with any instrument."""
        return validate_spectrum(request.spectrum, request.settings).model_dump(mode="json")

    @mcp.tool(name="spectra.fit_eds")
    def fit_eds(request: FitRequest) -> dict:
        """Fit approved demo candidate lines and return background, residuals, diagnostics and provenance."""
        return fit_spectrum(request).model_dump(mode="json")

    @mcp.tool(name="spectra.quantify_eds")
    def quantify_eds(request: FitRequest) -> dict:
        """Return screening-only normalized net-peak-area fractions; never interpret output as wt% or at%."""
        return quantify_spectrum(request).model_dump(mode="json")

    @mcp.tool(name="spectra.parse_emsa")
    def parse_emsa(request: ParseEmsaRequest) -> dict:
        """Parse a single EMSA/MAS text spectrum to the common EdsSpectrum contract."""
        return parse_emsa_text(
            case_id=request.case_id,
            asset_id=request.asset_id,
            emsa_text=request.emsa_text,
            calibration=request.calibration,
        ).model_dump(mode="json")

    @mcp.tool(name="spectra.line_catalog")
    def line_catalog() -> dict:
        """Return the limited demo reference line catalog and its explicit reference-status marker."""
        return catalog_response().model_dump(mode="json")

    return mcp


def main() -> None:
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()

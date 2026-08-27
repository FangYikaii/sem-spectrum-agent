"""Small, deliberately limited EDS line catalog for the reference implementation.

The energies in this file are approximate line centres for regression examples,
not a certified reference library. Production deployments must use an approved,
versioned line-catalog plugin tied to a traceable source and instrument setup.
"""

from __future__ import annotations

from .models import LineCatalogResponse, LineDefinition

CATALOG_ID = "semispectra-demo-lines"
CATALOG_VERSION = "0.1.0"
REFERENCE_STATUS = "demo_reference_only"

# Common semiconductor process / contamination-screening elements. Values are
# approximate characteristic X-ray line centres in eV and must not be used for
# release decisions or concentration reports.
DEMO_LINES: tuple[LineDefinition, ...] = (
    LineDefinition(element="C", line="Kα", energy_ev=277.0, family="K"),
    LineDefinition(element="N", line="Kα", energy_ev=392.4, family="K"),
    LineDefinition(element="O", line="Kα", energy_ev=524.9, family="K"),
    LineDefinition(element="F", line="Kα", energy_ev=676.8, family="K"),
    LineDefinition(element="Na", line="Kα", energy_ev=1040.9, family="K"),
    LineDefinition(element="Mg", line="Kα", energy_ev=1253.6, family="K"),
    LineDefinition(element="Al", line="Kα", energy_ev=1486.7, family="K"),
    LineDefinition(element="Si", line="Kα", energy_ev=1739.98, family="K"),
    LineDefinition(element="P", line="Kα", energy_ev=2013.7, family="K"),
    LineDefinition(element="S", line="Kα", energy_ev=2307.8, family="K"),
    LineDefinition(element="Cl", line="Kα", energy_ev=2622.4, family="K"),
    LineDefinition(element="K", line="Kα", energy_ev=3313.8, family="K"),
    LineDefinition(element="Ca", line="Kα", energy_ev=3691.7, family="K"),
    LineDefinition(element="Ti", line="Kα", energy_ev=4508.9, family="K"),
    LineDefinition(element="Cr", line="Kα", energy_ev=5414.7, family="K"),
    LineDefinition(element="Mn", line="Kα", energy_ev=5898.75, family="K"),
    LineDefinition(element="Fe", line="Kα", energy_ev=6404.0, family="K"),
    LineDefinition(element="Co", line="Kα", energy_ev=6930.3, family="K"),
    LineDefinition(element="Ni", line="Kα", energy_ev=7478.2, family="K"),
    LineDefinition(element="Cu", line="Kα", energy_ev=8047.8, family="K"),
    LineDefinition(element="W", line="Lα", energy_ev=8397.6, family="L"),
    LineDefinition(element="Zn", line="Kα", energy_ev=8638.9, family="K"),
    LineDefinition(element="Ga", line="Kα", energy_ev=9221.2, family="K"),
    LineDefinition(element="Ge", line="Kα", energy_ev=9886.4, family="K"),
    LineDefinition(element="As", line="Kα", energy_ev=10543.7, family="K"),
    LineDefinition(element="Mo", line="Kα", energy_ev=17479.3, family="K"),
)


def catalog_response() -> LineCatalogResponse:
    return LineCatalogResponse(
        catalog_id=CATALOG_ID,
        catalog_version=CATALOG_VERSION,
        reference_status=REFERENCE_STATUS,
        lines=list(DEMO_LINES),
    )


def lines_for_elements(elements: list[str]) -> list[LineDefinition]:
    requested = set(elements)
    return [line for line in DEMO_LINES if line.element in requested]


def supported_elements() -> set[str]:
    return {line.element for line in DEMO_LINES}

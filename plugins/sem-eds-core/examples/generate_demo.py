"""Generate a deterministic, non-production Si/O EDS fixture in EMSA/MAS text format."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def gaussian(energy: np.ndarray, centre: float, fwhm: float, area: float) -> np.ndarray:
    sigma = fwhm / 2.354820045
    profile = np.exp(-0.5 * ((energy - centre) / sigma) ** 2)
    return area * profile / np.trapezoid(profile, energy)


def main() -> None:
    energy = np.arange(0.0, 10240.0, 10.0)
    baseline = 18.0 + 0.003 * energy
    counts = baseline
    counts += gaussian(energy, 524.9, 105.0, 6_000.0)
    counts += gaussian(energy, 1486.7, 120.0, 3_000.0)
    counts += gaussian(energy, 1739.98, 125.0, 18_000.0)
    counts += 1.5 * np.sin(energy / 37.0)  # deterministic texture, not random noise
    counts = np.clip(counts, 0.0, None)

    header = [
        "#FORMAT      : EMSA/MAS Spectral Data File",
        "#VERSION     : 1.0",
        "#TITLE       : Synthetic Si/O/Al screening fixture",
        "#NPOINTS     : 1024",
        "#NCOLUMNS    : 1",
        "#XUNITS      : eV",
        "#YUNITS      : Counts",
        "#DATATYPE    : Y",
        "#XPERCHAN    : 10.0",
        "#OFFSET      : 0.0",
        "#CHOFFSET    : 0",
        "#SIGNALTYPE  : EDS",
        "#BEAMKV -kV  : 10.0",
        "#LIVETIME -s : 60.0",
        "#REALTIME -s : 72.0",
        "#EDSDET      : SYNTHETIC-130EV",
        "#SPECTRUM    : DATA BEGINS HERE",
    ]
    rows = [", ".join(f"{value:.6f}" for value in counts[index : index + 8]) for index in range(0, len(counts), 8)]
    target = Path(__file__).with_name("silicon_oxide_demo.emsa")
    target.write_text("\n".join(header + rows + ["#ENDOFDATA  :"]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

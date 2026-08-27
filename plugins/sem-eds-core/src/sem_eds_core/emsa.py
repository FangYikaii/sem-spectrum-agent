"""Parser for the text form of EMSA/MAS spectral-data exchange files.

This parser deliberately supports a strict, useful subset: #DATATYPE Y and XY,
#SPECTRUM / #ENDOFDATA boundaries, and common EDS metadata. It preserves all
header values because vendor-specific fields must not be silently discarded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .models import (
    CalibrationRef,
    EdsSpectrum,
    ParseEmsaResponse,
    SpectrumMetadata,
    ValidationIssue,
)

_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


class EmsaParseError(ValueError):
    """Raised when the declared EMSA/MAS structure cannot be safely parsed."""


@dataclass(frozen=True)
class HeaderValue:
    key: str
    value: str
    is_user_header: bool


def _normalise_key(key: str) -> str:
    return " ".join(key.strip().upper().split())


def _header_value(headers: dict[str, str], key: str) -> str | None:
    target = _normalise_key(key)
    if target in headers:
        return headers[target]
    for current_key, value in headers.items():
        if current_key.startswith(target + " ") or current_key.startswith(target + "-"):
            return value
    return None


def _float_from_header(headers: dict[str, str], key: str) -> float | None:
    raw = _header_value(headers, key)
    if raw is None:
        return None
    match = _NUMBER.search(raw)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_header_line(line: str) -> HeaderValue | None:
    if not line.startswith("#") or line.upper().startswith("#SPECTRUM") or line.upper().startswith("#ENDOFDATA"):
        return None
    content = line[1:]
    is_user_header = content.startswith("#")
    if is_user_header:
        content = content[1:]
    if ":" not in content:
        return None
    key, value = content.split(":", 1)
    return HeaderValue(_normalise_key(key), value.strip(), is_user_header)


def _parse_numeric_values(line: str) -> list[float]:
    tokens = [token for token in re.split(r"[,\s]+", line.strip()) if token]
    try:
        return [float(token) for token in tokens]
    except ValueError as exc:
        raise EmsaParseError(f"Non-numeric spectrum value in line: {line[:160]!r}") from exc


def parse_emsa_text(
    *, case_id: str, asset_id: str, emsa_text: str, calibration: CalibrationRef | None = None
) -> ParseEmsaResponse:
    """Parse EMSA/MAS ASCII content into the common `EdsSpectrum` contract."""

    headers: dict[str, str] = {}
    user_headers: dict[str, str] = {}
    data_lines: list[str] = []
    in_spectrum = False
    saw_spectrum = False
    saw_end = False

    for raw_line in emsa_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("#SPECTRUM"):
            if saw_spectrum:
                raise EmsaParseError("Multiple #SPECTRUM blocks are not supported for a single-spectrum request.")
            in_spectrum = True
            saw_spectrum = True
            continue
        if upper.startswith("#ENDOFDATA"):
            if not in_spectrum:
                raise EmsaParseError("#ENDOFDATA appears before #SPECTRUM.")
            saw_end = True
            in_spectrum = False
            break
        if in_spectrum:
            if line.startswith("#"):
                raise EmsaParseError("Unexpected header line inside #SPECTRUM data block.")
            data_lines.append(line)
            continue
        header = _parse_header_line(line)
        if header:
            destination = user_headers if header.is_user_header else headers
            destination[header.key] = header.value

    if not saw_spectrum:
        raise EmsaParseError("Missing required #SPECTRUM data boundary.")
    if not saw_end:
        raise EmsaParseError("Missing required #ENDOFDATA boundary.")
    if not data_lines:
        raise EmsaParseError("#SPECTRUM block contains no numeric data.")

    datatype = (_header_value(headers, "DATATYPE") or "").strip().upper()
    warnings: list[ValidationIssue] = []

    if datatype == "Y":
        values = [value for line in data_lines for value in _parse_numeric_values(line)]
        offset = _float_from_header(headers, "OFFSET")
        xperchan = _float_from_header(headers, "XPERCHAN")
        choffset = _float_from_header(headers, "CHOFFSET") or 0.0
        if offset is None or xperchan is None:
            raise EmsaParseError("DATATYPE Y requires numeric OFFSET and XPERCHAN headers.")
        if xperchan <= 0:
            raise EmsaParseError("XPERCHAN must be positive for DATATYPE Y.")
        energy = offset + (np.arange(len(values), dtype=float) + choffset) * xperchan
        counts = np.asarray(values, dtype=float)
    elif datatype == "XY":
        rows = [_parse_numeric_values(line) for line in data_lines]
        flattened = [value for row in rows for value in row]
        if len(flattened) % 2:
            raise EmsaParseError("DATATYPE XY requires an even count of numeric values (energy, count pairs).")
        pairs = np.asarray(flattened, dtype=float).reshape(-1, 2)
        energy = pairs[:, 0]
        counts = pairs[:, 1]
    else:
        raise EmsaParseError("Only DATATYPE Y and DATATYPE XY are supported by this plugin.")

    declared_points = _float_from_header(headers, "NPOINTS")
    if declared_points is not None and int(declared_points) != len(counts):
        warnings.append(
            ValidationIssue(
                code="npoints_mismatch",
                message=f"NPOINTS declares {int(declared_points)} but parsed {len(counts)} values.",
                field="NPOINTS",
            )
        )

    signal_type = _header_value(headers, "SIGNALTYPE") or "EDS"
    metadata = SpectrumMetadata(
        signal_type=signal_type,
        live_time_s=_float_from_header(headers, "LIVETIME"),
        real_time_s=_float_from_header(headers, "REALTIME"),
        beam_kv=_float_from_header(headers, "BEAMKV"),
        detector_id=_header_value(headers, "EDSDET"),
        source_format="emsa-mas",
        raw_headers=headers,
        user_headers=user_headers,
    )
    spectrum = EdsSpectrum(
        case_id=case_id,
        asset_id=asset_id,
        energy_ev=energy.tolist(),
        counts=counts.tolist(),
        metadata=metadata,
        calibration=calibration,
    )
    return ParseEmsaResponse(spectrum=spectrum, warnings=warnings)

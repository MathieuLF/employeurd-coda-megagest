from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class OutputPlan:
    directory: Path
    mnd_path: Path
    report_path: Path | None
    validation_json_path: Path | None


def build_output_plan(
    source_path: Path,
    output_root: Path,
    *,
    now: datetime | None = None,
    include_report: bool = True,
    include_validation_json: bool = True,
) -> OutputPlan:
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    safe_stem = _safe_stem(source_path.stem or "conversion")
    base_dir = output_root / timestamp
    directory = _next_available_directory(base_dir)
    mnd_path = directory / f"{safe_stem}.mnd"
    return OutputPlan(
        directory=directory,
        mnd_path=mnd_path,
        report_path=mnd_path.with_suffix(".rapport.md") if include_report else None,
        validation_json_path=mnd_path.with_suffix(".validation.json") if include_validation_json else None,
    )


def _next_available_directory(base_dir: Path) -> Path:
    if not base_dir.exists():
        return base_dir
    for index in range(2, 1000):
        candidate = base_dir.with_name(f"{base_dir.name}-{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("Impossible de trouver un dossier de sortie disponible.")


def _safe_stem(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return cleaned.strip("._") or "conversion"

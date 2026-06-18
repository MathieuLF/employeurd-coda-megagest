from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class ConversionError(Exception):
    """Raised when a source file cannot be converted safely."""


@dataclass(frozen=True)
class InspectResult:
    columns: list[str]
    row_count: int


@dataclass(frozen=True)
class ConversionResult:
    row_count: int
    total_debit: Decimal
    total_credit: Decimal


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            mapping = json.load(handle)
    except OSError as error:
        raise ConversionError(f"Impossible de lire le mapping: {path}") from error
    except json.JSONDecodeError as error:
        raise ConversionError(f"Mapping JSON invalide: {path}") from error

    if not isinstance(mapping, dict):
        raise ConversionError("Le mapping doit etre un objet JSON.")

    if not mapping.get("fields"):
        raise ConversionError("Le mapping doit definir au moins un champ de sortie.")

    return mapping


def inspect_file(path: Path, encoding: str = "utf-8-sig") -> InspectResult:
    rows = _read_source(path, delimiter="auto", encoding=encoding)
    columns = list(rows[0].keys()) if rows else []
    return InspectResult(columns=columns, row_count=len(rows))


def convert_file(input_path: Path, output_path: Path, mapping: dict[str, Any]) -> ConversionResult:
    input_config = mapping.get("input", {})
    output_config = mapping.get("output", {})
    delimiter = input_config.get("delimiter", "auto")
    source_encoding = input_config.get("encoding", "utf-8-sig")
    output_encoding = output_config.get("encoding", "cp1252")
    line_ending = output_config.get("line_ending", "\r\n")

    rows = _read_source(input_path, delimiter=delimiter, encoding=source_encoding)
    _validate_columns(rows, mapping)

    total_debit = _sum_amount(rows, mapping, "debit")
    total_credit = _sum_amount(rows, mapping, "credit")
    if mapping.get("validation", {}).get("require_balanced", False) and total_debit != total_credit:
        raise ConversionError(f"Ecritures non balancees: debit={total_debit:.2f}, credit={total_credit:.2f}")

    lines = [_render_line(row, mapping) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding=output_encoding, newline="") as handle:
        handle.write(line_ending.join(lines) + line_ending)

    return ConversionResult(row_count=len(rows), total_debit=total_debit, total_credit=total_credit)


def _read_source(path: Path, delimiter: str, encoding: str) -> list[dict[str, str]]:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        raise ConversionError("Les fichiers Excel doivent etre exportes en CSV avant conversion.")

    try:
        content = path.read_text(encoding=encoding)
    except OSError as error:
        raise ConversionError(f"Impossible de lire le fichier source: {path}") from error

    if not content.strip():
        raise ConversionError("Le fichier source est vide.")

    csv_delimiter = _detect_delimiter(content) if delimiter == "auto" else delimiter
    reader = csv.DictReader(content.splitlines(), delimiter=csv_delimiter)
    rows = [{key.strip(): (value or "").strip() for key, value in row.items() if key} for row in reader]

    if not reader.fieldnames:
        raise ConversionError("Le fichier source doit contenir une ligne d'en-tetes.")

    return rows


def _detect_delimiter(content: str) -> str:
    sample = "\n".join(content.splitlines()[:10])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _validate_columns(rows: list[dict[str, str]], mapping: dict[str, Any]) -> None:
    if not rows:
        raise ConversionError("Le fichier source ne contient aucune ligne de donnees.")

    available = set(rows[0].keys())
    columns = mapping.get("columns", {})
    missing = sorted(column for column in columns.values() if column not in available)
    if missing:
        raise ConversionError(f"Colonnes source manquantes: {', '.join(missing)}")


def _sum_amount(rows: list[dict[str, str]], mapping: dict[str, Any], logical_name: str) -> Decimal:
    column = mapping.get("columns", {}).get(logical_name)
    if not column:
        return Decimal("0")

    return sum((_parse_amount(row.get(column, "")) for row in rows), Decimal("0"))


def _render_line(row: dict[str, str], mapping: dict[str, Any]) -> str:
    rendered_fields = []
    for field in mapping["fields"]:
        rendered_fields.append(_render_field(row, field, mapping))
    return "".join(rendered_fields)


def _render_field(row: dict[str, str], field: dict[str, Any], mapping: dict[str, Any]) -> str:
    value = _field_value(row, field, mapping)
    value = _format_value(value, field, mapping)
    return _fit(value, int(field["width"]), field.get("align", "left"), field.get("pad", " "))


def _field_value(row: dict[str, str], field: dict[str, Any], mapping: dict[str, Any]) -> str:
    if "value" in field:
        return str(field["value"])

    source = field.get("source")
    if not source:
        return ""

    column = mapping.get("columns", {}).get(source, source)
    return row.get(column, "")


def _format_value(value: str, field: dict[str, Any], mapping: dict[str, Any]) -> str:
    format_name = field.get("format")
    if not format_name:
        return value

    if format_name == "date":
        formats = mapping.get("formats", {})
        input_format = formats.get("input_date", "%Y-%m-%d")
        output_format = formats.get("output_date", "%Y%m%d")
        try:
            return datetime.strptime(value, input_format).strftime(output_format)
        except ValueError as error:
            raise ConversionError(f"Date invalide: {value}") from error

    if format_name == "amount_cents":
        amount = _parse_amount(value)
        return str(int((amount * Decimal("100")).quantize(Decimal("1"))))

    raise ConversionError(f"Format de champ inconnu: {format_name}")


def _parse_amount(value: str) -> Decimal:
    cleaned = value.strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return Decimal("0")

    try:
        return Decimal(cleaned)
    except InvalidOperation as error:
        raise ConversionError(f"Montant invalide: {value}") from error


def _fit(value: str, width: int, align: str, pad: str) -> str:
    if width < 1:
        raise ConversionError("La largeur d'un champ doit etre superieure a zero.")

    if len(pad) != 1:
        raise ConversionError("Le caractere de remplissage doit avoir une longueur de 1.")

    text = value[:width]
    if align == "right":
        return text.rjust(width, pad)
    if align == "left":
        return text.ljust(width, pad)

    raise ConversionError(f"Alignement inconnu: {align}")

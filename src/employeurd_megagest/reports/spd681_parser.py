from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from employeurd_megagest.errors import ErrorDetail, FileOperationError, ValidationFailed
from employeurd_megagest.models import PayrollReportTotals


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
BATCH_PATTERN = re.compile(r"OPD_RP_(\d+)_SPD681", re.IGNORECASE)
DATE_PATTERNS = ("%Y-%m-%d", "%Y%m%d")
PROGRAM_COLUMNS = {
    "rrq": (13, 14, 15, 16),
    "ae": (20, 21, 22, 23),
    "rqap": (24, 25, 26, 27),
}


@dataclass(frozen=True)
class SPD681ProgramTotals:
    eligible_earnings: Decimal = ZERO
    paid: Decimal = ZERO
    expected: Decimal = ZERO
    difference: Decimal = ZERO


@dataclass(frozen=True)
class SPD681Report:
    source_file: Path
    row_count: int
    batch: str | None
    period: str | None
    report_date: date | None
    difference_threshold: Decimal
    totals_by_program: dict[str, SPD681ProgramTotals]
    max_absolute_difference: Decimal
    rows_with_reported_difference: int

    def to_payroll_totals(self) -> PayrollReportTotals:
        other_totals: dict[str, Decimal] = {
            "difference_threshold": self.difference_threshold,
            "max_absolute_difference": self.max_absolute_difference,
            "rows_with_reported_difference": Decimal(self.rows_with_reported_difference),
        }
        for program, totals in self.totals_by_program.items():
            other_totals[f"{program}_eligible_earnings"] = totals.eligible_earnings
            other_totals[f"{program}_paid"] = totals.paid
            other_totals[f"{program}_expected"] = totals.expected
            other_totals[f"{program}_difference"] = totals.difference
        return PayrollReportTotals(
            report_type="SPD681",
            source_file=self.source_file,
            period=self.period,
            pay_date=self.report_date,
            batch=self.batch,
            gross_pay=None,
            net_pay=None,
            employee_deductions=None,
            employer_contributions=None,
            vacation_pay=None,
            other_totals=other_totals,
        )


class SPD681Parser:
    report_type = "SPD681"

    def parse(self, path: Path) -> PayrollReportTotals:
        return parse_spd681_xml(path).to_payroll_totals()


def parse_spd681_xml(path: Path) -> SPD681Report:
    try:
        root = ET.parse(path).getroot()
    except OSError as error:
        raise FileOperationError(f"Impossible de lire le rapport SPD681: {path}") from error
    except ET.ParseError as error:
        raise ValidationFailed([ErrorDetail("spd681_xml", "Le fichier SPD681 XML est invalide.")]) from error

    rows = _worksheet_rows(root)
    header_index = _find_header_index(rows)
    if header_index is None:
        raise ValidationFailed([ErrorDetail("spd681_header", "En-tête SPD681 introuvable.")])

    errors: list[ErrorDetail] = []
    totals = {program: SPD681ProgramTotals() for program in PROGRAM_COLUMNS}
    max_abs = ZERO
    rows_with_difference = 0
    row_count = 0

    for row_offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(value.strip() for value in row):
            continue
        if not _looks_like_detail_row(row):
            continue

        row_count += 1
        row_has_difference = False
        for program, columns in PROGRAM_COLUMNS.items():
            eligible, paid, expected, difference = _parse_program_values(row, columns, row_offset, program, errors)
            calculated_difference = (expected - paid).quantize(CENT)
            if difference != calculated_difference:
                errors.append(
                    ErrorDetail(
                        "spd681_difference_mismatch",
                        f"Écart {program.upper()} incohérent avec les cotisations payées et prévues.",
                        row_offset,
                        program,
                    )
                )
            totals[program] = _add_program_totals(totals[program], eligible, paid, expected, difference)
            if difference.copy_abs() > ZERO:
                row_has_difference = True
                max_abs = max(max_abs, difference.copy_abs())
        if row_has_difference:
            rows_with_difference += 1

    if row_count == 0:
        errors.append(ErrorDetail("spd681_empty", "Le rapport SPD681 ne contient aucune ligne de détail."))
    if errors:
        raise ValidationFailed(errors)

    report_date = _find_report_date(rows[:header_index])
    return SPD681Report(
        source_file=path,
        row_count=row_count,
        batch=_batch_from_filename(path),
        period=report_date.strftime("%Y%m") if report_date else None,
        report_date=report_date,
        difference_threshold=_find_difference_threshold(rows[:header_index]),
        totals_by_program=totals,
        max_absolute_difference=max_abs,
        rows_with_reported_difference=rows_with_difference,
    )


def _worksheet_rows(root: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for element in root.iter():
        if _local_name(element.tag) != "Row":
            continue
        values: list[str] = []
        position = 1
        for cell in element:
            if _local_name(cell.tag) != "Cell":
                continue
            index = cell.attrib.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
            if index:
                while position < int(index):
                    values.append("")
                    position += 1
            values.append(_cell_text(cell).strip())
            position += 1
        rows.append(values)
    return rows


def _cell_text(cell: ET.Element) -> str:
    for child in cell:
        if _local_name(child.tag) == "Data":
            return child.text or ""
    return ""


def _find_header_index(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows):
        lowered = [value.strip().lower() for value in row]
        if lowered[:3] == ["matricule", "nom", "prénom"] and lowered.count("écart") >= 3:
            return index
    return None


def _looks_like_detail_row(row: list[str]) -> bool:
    if len(row) < 27:
        return False
    if not row[0].strip():
        return False
    return any(row[column - 1].strip() for columns in PROGRAM_COLUMNS.values() for column in columns)


def _parse_program_values(
    row: list[str],
    columns: tuple[int, int, int, int],
    row_number: int,
    program: str,
    errors: list[ErrorDetail],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    parsed = []
    for column in columns:
        parsed.append(_parse_decimal(_get(row, column), row_number, f"{program}_{column}", errors))
    return tuple(parsed)  # type: ignore[return-value]


def _parse_decimal(value: str, row_number: int, field_name: str, errors: list[ErrorDetail]) -> Decimal:
    cleaned = value.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if cleaned.startswith("."):
        cleaned = "0" + cleaned
    if cleaned.startswith("-."):
        cleaned = "-0." + cleaned[2:]
    if not cleaned:
        return ZERO
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        errors.append(ErrorDetail("spd681_decimal", "Montant SPD681 invalide.", row_number, field_name))
        return ZERO
    if parsed != parsed.quantize(CENT):
        errors.append(ErrorDetail("spd681_decimal_scale", "Montant SPD681 avec plus de 2 décimales.", row_number, field_name))
    return parsed


def _add_program_totals(
    totals: SPD681ProgramTotals,
    eligible: Decimal,
    paid: Decimal,
    expected: Decimal,
    difference: Decimal,
) -> SPD681ProgramTotals:
    return SPD681ProgramTotals(
        eligible_earnings=totals.eligible_earnings + eligible,
        paid=totals.paid + paid,
        expected=totals.expected + expected,
        difference=totals.difference + difference,
    )


def _find_report_date(rows: list[list[str]]) -> date | None:
    for row in rows:
        for value in row:
            cleaned = value.strip()
            for pattern in DATE_PATTERNS:
                try:
                    return datetime.strptime(cleaned, pattern).date()
                except ValueError:
                    pass
    return None


def _find_difference_threshold(rows: list[list[str]]) -> Decimal:
    for row in rows:
        if not any(value.strip().lower() == "écart minimum" for value in row):
            continue
        for value in row:
            errors: list[ErrorDetail] = []
            parsed = _parse_decimal(value, 0, "difference_threshold", errors)
            if not errors and parsed > ZERO:
                return parsed
    return ZERO


def _get(row: list[str], one_based_column: int) -> str:
    index = one_based_column - 1
    return row[index] if index < len(row) else ""


def _batch_from_filename(path: Path) -> str | None:
    match = BATCH_PATTERN.search(path.name)
    return match.group(1) if match else None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

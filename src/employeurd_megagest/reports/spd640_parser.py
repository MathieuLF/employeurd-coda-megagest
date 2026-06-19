from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from employeurd_megagest.config import ReportComponentConfig, ReportTotalConfig, SPD640Config
from employeurd_megagest.errors import ErrorDetail, FileOperationError, ValidationFailed
from employeurd_megagest.models import PayrollReportTotals


REQUIRED_COLUMNS = (
    "COMPAGNIE",
    "DATE COMPTABLE",
    "DIV. OU TRA#1",
    "SERV. OU TRA#2",
    "DEPT. OU TRA#3",
    "S-DEPT. OU TRA#4",
    "TRA#5",
    "TRA#6",
    "RELEVES",
    "DATE",
    "MATRICULE",
    "NOM, PRENOM",
    "TYPE",
    "CODE",
    "DESCRIPTION CODE",
    "QUANTITES",
    "TAUX",
    "MONTANTS",
    "MNTS/EMPLOYEUR",
    "QUANTITES BANQUE",
    "MNTS BANQUE",
)
MONEY_FIELDS = ("MONTANTS", "MNTS/EMPLOYEUR", "MNTS BANQUE")
BATCH_PATTERN = re.compile(r"OPD_RP_(\d+)_SPD640", re.IGNORECASE)
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class SPD640Report:
    source_file: Path
    row_count: int
    batch: str | None
    period: str | None
    accounting_dates: tuple[date, ...]
    totals: dict[str, Decimal]
    totals_by_type: dict[str, dict[str, Decimal]]
    totals_by_type_code: dict[tuple[str, str], dict[str, Decimal]]
    descriptions_by_type_code: dict[tuple[str, str], str] = field(default_factory=dict)

    def to_payroll_totals(self) -> PayrollReportTotals:
        pay_date = self.accounting_dates[0] if len(self.accounting_dates) == 1 else None
        return PayrollReportTotals(
            report_type="SPD640",
            source_file=self.source_file,
            period=self.period,
            pay_date=pay_date,
            batch=self.batch,
            gross_pay=self.totals_by_type.get("G", {}).get("MONTANTS", ZERO),
            net_pay=None,
            employee_deductions=self.totals_by_type.get("D", {}).get("MONTANTS", ZERO),
            employer_contributions=self.totals.get("MNTS/EMPLOYEUR", ZERO),
            vacation_pay=self.totals.get("MNTS BANQUE", ZERO),
            other_totals={
                "montants": self.totals.get("MONTANTS", ZERO),
                "mnts_employeur": self.totals.get("MNTS/EMPLOYEUR", ZERO),
                "mnts_banque": self.totals.get("MNTS BANQUE", ZERO),
                "type_g_montants": self.totals_by_type.get("G", {}).get("MONTANTS", ZERO),
                "type_d_montants": self.totals_by_type.get("D", {}).get("MONTANTS", ZERO),
            },
        )


@dataclass(frozen=True)
class SPD640ReconciliationResult:
    ok: bool
    source_debit: Decimal
    source_credit: Decimal
    report_debit: Decimal
    report_credit: Decimal
    debit_difference: Decimal
    credit_difference: Decimal
    tolerance: Decimal
    debit_label: str
    credit_label: str


class SPD640Parser:
    report_type = "SPD640"

    def parse(self, path: Path) -> PayrollReportTotals:
        return parse_spd640_csv(path).to_payroll_totals()


def parse_spd640_csv(path: Path, *, encoding: str = "utf-8-sig") -> SPD640Report:
    try:
        handle = path.open("r", encoding=encoding, newline="")
    except OSError as error:
        raise FileOperationError(f"Impossible de lire le rapport SPD640: {path}") from error

    with handle:
        reader = csv.DictReader(handle, delimiter=";")
        headers = tuple(reader.fieldnames or ())
        _validate_headers(headers)

        row_count = 0
        errors: list[ErrorDetail] = []
        totals = _empty_money_totals()
        totals_by_type: dict[str, dict[str, Decimal]] = defaultdict(_empty_money_totals)
        totals_by_type_code: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(_empty_money_totals)
        descriptions_by_type_code: dict[tuple[str, str], str] = {}
        accounting_dates: set[date] = set()

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            if None in row:
                errors.append(ErrorDetail("spd640_extra_columns", "Colonnes supplémentaires détectées.", row_number))
                continue

            row_type = (row.get("TYPE") or "").strip()
            code = (row.get("CODE") or "").strip()
            description = (row.get("DESCRIPTION CODE") or "").strip()
            if row_type not in {"G", "D"}:
                errors.append(ErrorDetail("spd640_type", "TYPE doit être G ou D.", row_number, "TYPE"))
            if not code:
                errors.append(ErrorDetail("spd640_code", "CODE est obligatoire.", row_number, "CODE"))

            accounting_date = _parse_date(row.get("DATE COMPTABLE", ""), row_number, errors)
            if accounting_date:
                accounting_dates.add(accounting_date)

            parsed_amounts = {}
            for field_name in MONEY_FIELDS:
                parsed_amounts[field_name] = _parse_decimal(row.get(field_name, ""), row_number, field_name, errors)

            if errors and errors[-1].line_number == row_number:
                continue

            key = (row_type, code)
            descriptions_by_type_code.setdefault(key, description)
            for field_name, amount in parsed_amounts.items():
                totals[field_name] += amount
                totals_by_type[row_type][field_name] += amount
                totals_by_type_code[key][field_name] += amount

    if row_count == 0:
        errors.append(ErrorDetail("spd640_empty", "Le rapport SPD640 ne contient aucune ligne."))
    if errors:
        raise ValidationFailed(errors)

    dates = tuple(sorted(accounting_dates))
    return SPD640Report(
        source_file=path,
        row_count=row_count,
        batch=_batch_from_filename(path),
        period=dates[0].strftime("%Y%m") if len(dates) == 1 else None,
        accounting_dates=dates,
        totals=dict(totals),
        totals_by_type={key: dict(value) for key, value in totals_by_type.items()},
        totals_by_type_code={key: dict(value) for key, value in totals_by_type_code.items()},
        descriptions_by_type_code=descriptions_by_type_code,
    )


def evaluate_report_total(report: SPD640Report, total_config: ReportTotalConfig) -> Decimal:
    total = ZERO
    for component in total_config.components:
        total += _evaluate_component(report, component)
    return total


def reconcile_spd640_with_source_totals(
    report: SPD640Report,
    *,
    source_debit: Decimal,
    source_credit: Decimal,
    config: SPD640Config,
) -> SPD640ReconciliationResult:
    if config.debit_total is None or config.credit_total is None:
        raise ValidationFailed("La configuration SPD640 doit définir debit_total et credit_total.")

    report_debit = evaluate_report_total(report, config.debit_total)
    report_credit = evaluate_report_total(report, config.credit_total)
    debit_difference = source_debit - report_debit
    credit_difference = source_credit - report_credit
    ok = abs(debit_difference) <= config.tolerance and abs(credit_difference) <= config.tolerance
    return SPD640ReconciliationResult(
        ok=ok,
        source_debit=source_debit,
        source_credit=source_credit,
        report_debit=report_debit,
        report_credit=report_credit,
        debit_difference=debit_difference,
        credit_difference=credit_difference,
        tolerance=config.tolerance,
        debit_label=config.debit_total.label,
        credit_label=config.credit_total.label,
    )


def _evaluate_component(report: SPD640Report, component: ReportComponentConfig) -> Decimal:
    total = ZERO
    for (row_type, code), values in report.totals_by_type_code.items():
        if component.type is not None and row_type != component.type:
            continue
        if component.codes and code not in component.codes:
            continue
        if component.exclude_codes and code in component.exclude_codes:
            continue
        total += values.get(component.field, ZERO) * component.sign
    return total


def _validate_headers(headers: tuple[str, ...]) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        raise ValidationFailed([ErrorDetail("spd640_missing_columns", f"Colonnes manquantes: {', '.join(missing)}")])


def _empty_money_totals() -> dict[str, Decimal]:
    return {field_name: ZERO for field_name in MONEY_FIELDS}


def _parse_decimal(value: str | None, row_number: int, field_name: str, errors: list[ErrorDetail]) -> Decimal:
    cleaned = (value or "").strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        return ZERO
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        errors.append(ErrorDetail("spd640_decimal", "Montant invalide.", row_number, field_name))
        return ZERO
    if parsed != parsed.quantize(Decimal("0.01")) and field_name != "TAUX":
        errors.append(ErrorDetail("spd640_decimal_scale", "Montant avec plus de 2 décimales.", row_number, field_name))
    return parsed


def _parse_date(value: str | None, row_number: int, errors: list[ErrorDetail]) -> date | None:
    cleaned = (value or "").strip()
    if not cleaned:
        errors.append(ErrorDetail("spd640_accounting_date", "DATE COMPTABLE est obligatoire.", row_number, "DATE COMPTABLE"))
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    errors.append(ErrorDetail("spd640_accounting_date", "DATE COMPTABLE invalide.", row_number, "DATE COMPTABLE"))
    return None


def _batch_from_filename(path: Path) -> str | None:
    match = BATCH_PATTERN.search(path.name)
    return match.group(1) if match else None

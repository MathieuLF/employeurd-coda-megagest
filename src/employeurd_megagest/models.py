from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal


Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class EmployeurDEntry:
    line_number: int
    batch: str
    account: str
    amount: Decimal
    entry_date: date
    raw_line: str


@dataclass(frozen=True)
class MndEntry:
    line_number: int
    account: str
    period: str
    reference: str
    entry_date: date
    source_label: str
    extra: str
    debit: Decimal
    credit: Decimal
    batch: str
    date2: date
    source_account: str | None = None


@dataclass(frozen=True)
class ValidationMessage:
    severity: Severity
    code: str
    message: str
    line_number: int | None = None
    field: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    messages: list[ValidationMessage] = field(default_factory=list)


@dataclass(frozen=True)
class ReconciliationResult:
    report_type: str
    status: Literal["success", "failed", "skipped"]
    required: bool
    report_path: Path | None
    source_debit: Decimal
    source_credit: Decimal
    report_debit: Decimal
    report_credit: Decimal
    debit_difference: Decimal
    credit_difference: Decimal
    tolerance: Decimal
    debit_label: str
    credit_label: str
    source_batch: str | None
    report_batch: str | None
    source_period: str | None
    report_period: str | None
    source_dates: tuple[str, ...] = ()
    report_dates: tuple[str, ...] = ()
    details: dict[str, str] = field(default_factory=dict)
    messages: list[ValidationMessage] = field(default_factory=list)


@dataclass(frozen=True)
class ConversionResult:
    status: Literal["success", "failed"]
    source_path: Path
    output_path: Path | None
    report_path: Path | None
    validation_json_path: Path | None
    row_count: int
    total_debit: Decimal
    total_credit: Decimal
    period: str | None
    batch: str | None
    entry_date: str | None = None
    account_count: int | None = None
    unknown_account_count: int = 0
    source_sha256: str | None = None
    mnd_sha256: str | None = None
    messages: list[ValidationMessage] = field(default_factory=list)
    reconciliations: list[ReconciliationResult] = field(default_factory=list)


@dataclass(frozen=True)
class PayrollReportTotals:
    report_type: str
    source_file: Path
    period: str | None
    pay_date: date | None
    batch: str | None
    gross_pay: Decimal | None
    net_pay: Decimal | None
    employee_deductions: Decimal | None
    employer_contributions: Decimal | None
    vacation_pay: Decimal | None
    other_totals: dict[str, Decimal]

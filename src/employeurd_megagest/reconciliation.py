from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .config import AppConfig
from .errors import ValidationFailed
from .models import EmployeurDEntry, ReconciliationResult, ValidationMessage
from .reports.gl_detail_pdf_parser import Side, parse_gl_detail_pdf
from .validator import convert_account, source_totals


ZERO = Decimal("0.00")
MAX_ACCOUNT_MISMATCH_DETAILS = 8


def reconcile_gl_detail(
    entries: list[EmployeurDEntry],
    report_path: Path,
    config: AppConfig,
    *,
    required: bool | None = None,
) -> ReconciliationResult:
    gl_config = config.reports.gl_detail
    is_required = _is_required(gl_config.mode) if required is None else required
    if not gl_config.enabled:
        return ReconciliationResult(
            report_type="GL_DETAIL",
            status="skipped",
            required=is_required,
            report_path=report_path,
            source_debit=ZERO,
            source_credit=ZERO,
            report_debit=ZERO,
            report_credit=ZERO,
            debit_difference=ZERO,
            credit_difference=ZERO,
            tolerance=gl_config.tolerance,
            debit_label="Grand détail GL désactivé",
            credit_label="Grand détail GL désactivé",
            source_batch=None,
            report_batch=None,
            source_period=None,
            report_period=None,
            messages=[ValidationMessage("info", "gl_detail_disabled", "Le rapprochement GL PDF est désactivé.")],
        )

    source_debit, source_credit = source_totals(entries)
    report = parse_gl_detail_pdf(report_path)
    debit_difference = source_debit - report.debit_total
    credit_difference = source_credit - report.credit_total

    source_batches = sorted({entry.batch for entry in entries})
    source_dates = tuple(sorted({entry.entry_date.isoformat() for entry in entries}))
    source_periods = sorted({entry.entry_date.strftime("%Y%m") for entry in entries})
    source_batch = source_batches[0] if len(source_batches) == 1 else None
    source_period = source_periods[0] if len(source_periods) == 1 else None
    report_dates = (report.accounting_date.isoformat(),) if report.accounting_date else ()
    source_account_totals = _source_account_side_totals(entries, config)
    account_mismatches = _account_side_mismatches(
        source_account_totals,
        report.account_side_totals,
        tolerance=gl_config.tolerance,
    )

    messages = []
    if abs(debit_difference) > gl_config.tolerance or abs(credit_difference) > gl_config.tolerance:
        messages.append(
            ValidationMessage(
                "error" if is_required else "warning",
                "gl_detail_amount_mismatch",
                f"Écart GL PDF: débit={debit_difference:.2f}, crédit={credit_difference:.2f}.",
            )
        )
    if gl_config.require_account_totals and account_mismatches:
        messages.append(
            ValidationMessage(
                "error" if is_required else "warning",
                "gl_detail_account_mismatch",
                f"{len(account_mismatches)} compte(s) GL ne concordent pas avec le PDF.",
            )
        )
    if gl_config.require_matching_date and source_dates and report_dates and source_dates != report_dates:
        messages.append(
            ValidationMessage(
                "error" if is_required else "warning",
                "gl_detail_date_mismatch",
                "La date du PDF GL ne concorde pas avec l'écriture.",
            )
        )

    details = {
        "company": report.company or "n/d",
        "accounting_period": report.accounting_period or "n/d",
        "payroll_period": report.payroll_period or "n/d",
        "line_count": str(report.row_count),
        "subtotal_count": str(report.subtotal_count),
        "account_mismatch_count": str(len(account_mismatches)),
    }
    for index, mismatch in enumerate(account_mismatches[:MAX_ACCOUNT_MISMATCH_DETAILS], start=1):
        details[f"account_mismatch_{index}"] = mismatch

    failed = any(message.severity == "error" for message in messages)
    return ReconciliationResult(
        report_type="GL_DETAIL",
        status="failed" if failed else "success",
        required=is_required,
        report_path=report_path,
        source_debit=source_debit,
        source_credit=source_credit,
        report_debit=report.debit_total,
        report_credit=report.credit_total,
        debit_difference=debit_difference,
        credit_difference=credit_difference,
        tolerance=gl_config.tolerance,
        debit_label="Total débit du PDF GL",
        credit_label="Total crédit du PDF GL",
        source_batch=source_batch,
        report_batch=None,
        source_period=source_period,
        report_period=report.period,
        source_dates=source_dates,
        report_dates=report_dates,
        details=details,
        messages=messages,
    )


def reconcile_control_report(
    entries: list[EmployeurDEntry],
    report_path: Path,
    config: AppConfig,
    *,
    required: bool | None = None,
) -> ReconciliationResult:
    name = report_path.name.lower()
    suffix = report_path.suffix.lower()
    if suffix == ".pdf" or "détail des imputations comptables" in name or "detail des imputations comptables" in name:
        return reconcile_gl_detail(entries, report_path, config, required=required)
    raise ValidationFailed("Type de rapport de contrôle non reconnu. Utilisez le PDF grand détail GL original.")


def reconciliation_failed(result: ReconciliationResult) -> bool:
    return result.required and result.status == "failed"


def _is_required(mode: str) -> bool:
    return mode.lower() in {"required", "strict", "blocking", "bloquant"}


def _source_account_side_totals(entries: list[EmployeurDEntry], config: AppConfig) -> dict[tuple[str, Side], Decimal]:
    totals: dict[tuple[str, Side], Decimal] = {}
    for entry in entries:
        if entry.amount == ZERO:
            continue
        account = convert_account(entry.account, config.accounts)
        side: Side = "debit" if entry.amount > ZERO else "credit"
        amount = entry.amount if entry.amount > ZERO else -entry.amount
        key = (account, side)
        totals[key] = totals.get(key, ZERO) + amount
    return totals


def _account_side_mismatches(
    source_totals_by_account: dict[tuple[str, Side], Decimal],
    report_totals_by_account: dict[tuple[str, Side], Decimal],
    *,
    tolerance: Decimal,
) -> list[str]:
    mismatches = []
    all_keys = sorted(set(source_totals_by_account) | set(report_totals_by_account))
    for account, side in all_keys:
        source_amount = source_totals_by_account.get((account, side), ZERO)
        report_amount = report_totals_by_account.get((account, side), ZERO)
        difference = source_amount - report_amount
        if abs(difference) <= tolerance:
            continue
        side_label = "débit" if side == "debit" else "crédit"
        mismatches.append(
            f"{account} {side_label}: source={source_amount:.2f}, pdf={report_amount:.2f}, écart={difference:.2f}"
        )
    return mismatches

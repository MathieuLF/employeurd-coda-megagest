from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .config import AppConfig
from .errors import ValidationFailed
from .models import EmployeurDEntry, ReconciliationResult, ValidationMessage
from .reports.gl_detail_pdf_parser import Side, parse_gl_detail_pdf
from .reports.spd640_parser import parse_spd640_csv, reconcile_spd640_with_source_totals
from .validator import convert_account, source_totals


ZERO = Decimal("0.00")
MAX_ACCOUNT_MISMATCH_DETAILS = 8


def reconcile_spd640(
    entries: list[EmployeurDEntry],
    report_path: Path,
    config: AppConfig,
    *,
    required: bool | None = None,
) -> ReconciliationResult:
    spd640_config = config.reports.spd640
    is_required = _is_required(spd640_config.mode) if required is None else required
    if not spd640_config.enabled:
        return ReconciliationResult(
            report_type="SPD640",
            status="skipped",
            required=is_required,
            report_path=report_path,
            source_debit=ZERO,
            source_credit=ZERO,
            report_debit=ZERO,
            report_credit=ZERO,
            debit_difference=ZERO,
            credit_difference=ZERO,
            tolerance=spd640_config.tolerance,
            debit_label="SPD640 désactivé",
            credit_label="SPD640 désactivé",
            source_batch=None,
            report_batch=None,
            source_period=None,
            report_period=None,
            messages=[ValidationMessage("info", "spd640_disabled", "Le rapprochement SPD640 est désactivé.")],
        )

    source_debit, source_credit = source_totals(entries)
    report = parse_spd640_csv(report_path)
    amount_result = reconcile_spd640_with_source_totals(
        report,
        source_debit=source_debit,
        source_credit=source_credit,
        config=spd640_config,
    )

    source_batches = sorted({entry.batch for entry in entries})
    source_dates = tuple(sorted({entry.entry_date.isoformat() for entry in entries}))
    source_periods = sorted({entry.entry_date.strftime("%Y%m") for entry in entries})
    source_batch = source_batches[0] if len(source_batches) == 1 else None
    source_period = source_periods[0] if len(source_periods) == 1 else None
    report_dates = tuple(date.isoformat() for date in report.accounting_dates)

    messages = []
    if not amount_result.ok:
        messages.append(
            ValidationMessage(
                "error" if is_required else "warning",
                "spd640_amount_mismatch",
                f"Écart SPD640: débit={amount_result.debit_difference:.2f}, crédit={amount_result.credit_difference:.2f}.",
            )
        )
    if spd640_config.require_matching_batch and (not source_batch or not report.batch or source_batch != report.batch):
        messages.append(
            ValidationMessage(
                "error" if is_required else "warning",
                "spd640_batch_mismatch",
                f"Lot TXT {source_batch or 'n/d'} différent du lot SPD640 {report.batch or 'n/d'}.",
            )
        )
    if spd640_config.require_matching_period and (not source_period or not report.period or source_period != report.period):
        messages.append(
            ValidationMessage(
                "error" if is_required else "warning",
                "spd640_period_mismatch",
                f"Période TXT {source_period or 'n/d'} différente de la période SPD640 {report.period or 'n/d'}.",
            )
        )
    if spd640_config.require_matching_date and source_dates and report_dates and source_dates != report_dates:
        messages.append(
            ValidationMessage(
                "error" if is_required else "warning",
                "spd640_date_mismatch",
                "Les dates TXT et SPD640 ne concordent pas.",
            )
        )

    failed = any(message.severity == "error" for message in messages)
    return ReconciliationResult(
        report_type="SPD640",
        status="failed" if failed else "success",
        required=is_required,
        report_path=report_path,
        source_debit=amount_result.source_debit,
        source_credit=amount_result.source_credit,
        report_debit=amount_result.report_debit,
        report_credit=amount_result.report_credit,
        debit_difference=amount_result.debit_difference,
        credit_difference=amount_result.credit_difference,
        tolerance=amount_result.tolerance,
        debit_label=amount_result.debit_label,
        credit_label=amount_result.credit_label,
        source_batch=source_batch,
        report_batch=report.batch,
        source_period=source_period,
        report_period=report.period,
        source_dates=source_dates,
        report_dates=report_dates,
        messages=messages,
    )


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
    if "spd640" in name or suffix == ".csv":
        return reconcile_spd640(entries, report_path, config, required=required)
    raise ValidationFailed("Type de rapport de contrôle non reconnu. Utilisez un PDF grand détail GL ou un SPD640-P CSV.")


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

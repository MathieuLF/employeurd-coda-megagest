from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .config import AppConfig
from .models import EmployeurDEntry, ReconciliationResult, ValidationMessage
from .reports.spd640_parser import parse_spd640_csv, reconcile_spd640_with_source_totals
from .validator import source_totals


ZERO = Decimal("0.00")


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


def reconciliation_failed(result: ReconciliationResult) -> bool:
    return result.required and result.status == "failed"


def _is_required(mode: str) -> bool:
    return mode.lower() in {"required", "strict", "blocking", "bloquant"}

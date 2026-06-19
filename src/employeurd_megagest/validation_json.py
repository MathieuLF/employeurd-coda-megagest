from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import ConversionResult
from .version import __version__


def build_validation_payload(result: ConversionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(result.source_path),
        "output_path": str(result.output_path) if result.output_path else None,
        "report_path": str(result.report_path) if result.report_path else None,
        "validation_json_path": str(result.validation_json_path) if result.validation_json_path else None,
        "row_count": result.row_count,
        "total_debit": _decimal(result.total_debit),
        "total_credit": _decimal(result.total_credit),
        "difference": _decimal(abs(result.total_debit - result.total_credit)),
        "period": result.period,
        "batch": result.batch,
        "entry_date": result.entry_date,
        "account_count": result.account_count,
        "unknown_account_count": result.unknown_account_count,
        "source_sha256": result.source_sha256,
        "mnd_sha256": result.mnd_sha256,
        "messages": [asdict(message) for message in result.messages],
        "reconciliations": [_reconciliation_payload(reconciliation) for reconciliation in result.reconciliations],
    }


def build_validation_json(result: ConversionResult) -> str:
    return json.dumps(build_validation_payload(result), ensure_ascii=False, indent=2) + "\n"


def default_validation_json_path(output_path: Path) -> Path:
    return output_path.with_suffix(".validation.json")


def _decimal(value: Decimal) -> str:
    return f"{value:.2f}"


def _reconciliation_payload(reconciliation) -> dict[str, Any]:
    return {
        "report_type": reconciliation.report_type,
        "status": reconciliation.status,
        "required": reconciliation.required,
        "report_path": str(reconciliation.report_path) if reconciliation.report_path else None,
        "source_debit": _decimal(reconciliation.source_debit),
        "source_credit": _decimal(reconciliation.source_credit),
        "report_debit": _decimal(reconciliation.report_debit),
        "report_credit": _decimal(reconciliation.report_credit),
        "debit_difference": _decimal(reconciliation.debit_difference),
        "credit_difference": _decimal(reconciliation.credit_difference),
        "tolerance": _decimal(reconciliation.tolerance),
        "debit_label": reconciliation.debit_label,
        "credit_label": reconciliation.credit_label,
        "source_batch": reconciliation.source_batch,
        "report_batch": reconciliation.report_batch,
        "source_period": reconciliation.source_period,
        "report_period": reconciliation.report_period,
        "source_dates": list(reconciliation.source_dates),
        "report_dates": list(reconciliation.report_dates),
        "messages": [asdict(message) for message in reconciliation.messages],
    }

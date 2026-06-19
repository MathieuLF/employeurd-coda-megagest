from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .config import AppConfig
from .errors import ErrorDetail, FileOperationError, ValidationFailed
from .models import ConversionResult, EmployeurDEntry, MndEntry, ReconciliationResult, ValidationMessage
from .parser_employeurd import parse_employeurd_file
from .parser_mnd import parse_mnd_text
from .report_markdown import build_markdown_report, default_report_path
from .validation_json import build_validation_json, default_validation_json_path
from .validator import (
    compare_roundtrip,
    convert_to_mnd_entries,
    mnd_totals,
    source_totals,
    validate_mnd_entries,
    validate_source_entries,
)
from .writer_mnd import write_mnd_text


ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ConversionDraft:
    source_entries: list[EmployeurDEntry]
    mnd_entries: list[MndEntry]
    mnd_text: str
    source_sha256: str
    mnd_sha256: str


def inspect_source(path: Path, config: AppConfig) -> ConversionResult:
    source_hash = _sha256_file(path)
    entries = parse_employeurd_file(path, reject_non_crlf=config.validation.reject_non_crlf_source)
    validate_source_entries(entries, config.validation)
    debit, credit = source_totals(entries)
    return ConversionResult(
        status="success",
        source_path=path,
        output_path=None,
        report_path=None,
        validation_json_path=None,
        row_count=len(entries),
        total_debit=debit,
        total_credit=credit,
        period=entries[0].entry_date.strftime("%Y%m") if entries else None,
        batch=entries[0].batch if entries else None,
        entry_date=entries[0].entry_date.isoformat() if entries else None,
        account_count=len({entry.account for entry in entries}),
        unknown_account_count=0,
        source_sha256=source_hash,
        mnd_sha256=None,
        messages=[],
    )


def build_conversion_draft(source_path: Path, config: AppConfig, *, period: str | None = None) -> ConversionDraft:
    source_hash = _sha256_file(source_path)
    source_entries = parse_employeurd_file(source_path, reject_non_crlf=config.validation.reject_non_crlf_source)
    validate_source_entries(source_entries, config.validation)
    mnd_entries = convert_to_mnd_entries(
        source_entries,
        account_config=config.accounts,
        mnd_config=config.mnd,
        validation_config=config.validation,
        period_override=period,
    )
    validate_mnd_entries(mnd_entries, config.validation)
    mnd_text = write_mnd_text(mnd_entries)
    if config.validation.require_mnd_roundtrip:
        parsed_back = parse_mnd_text(mnd_text, require_crlf=config.validation.require_crlf_mnd_output)
        compare_roundtrip(mnd_entries, parsed_back)
    mnd_hash = hashlib.sha256(mnd_text.encode(config.mnd.output_encoding)).hexdigest()
    return ConversionDraft(
        source_entries=source_entries,
        mnd_entries=mnd_entries,
        mnd_text=mnd_text,
        source_sha256=source_hash,
        mnd_sha256=mnd_hash,
    )


def validate_file(
    source_path: Path,
    config: AppConfig,
    *,
    period: str | None = None,
    report_path: Path | None = None,
    validation_json_path: Path | None = None,
    overwrite: bool = False,
    reconciliations: list[ReconciliationResult] | None = None,
) -> ConversionResult:
    reconciliations = reconciliations or []
    reconciliation_errors = _reconciliation_error_details(reconciliations)
    if reconciliation_errors:
        result = _failed_result(source_path, None, report_path, validation_json_path, reconciliation_errors, reconciliations)
        _write_artifacts(result, overwrite=overwrite)
        raise ValidationFailed(reconciliation_errors)
    try:
        draft = build_conversion_draft(source_path, config, period=period)
    except ValidationFailed as error:
        result = _failed_result(source_path, None, report_path, validation_json_path, error.errors, reconciliations)
        _write_artifacts(result, overwrite=overwrite)
        raise

    all_reconciliations = [_mnd_source_reconciliation(draft, config.validation.debit_credit_tolerance), *reconciliations]
    mnd_reconciliation_errors = _reconciliation_error_details(all_reconciliations[:1])
    if mnd_reconciliation_errors:
        result = _failed_result(source_path, None, report_path, validation_json_path, mnd_reconciliation_errors, all_reconciliations)
        _write_artifacts(result, overwrite=overwrite)
        raise ValidationFailed(mnd_reconciliation_errors)

    debit, credit = mnd_totals(draft.mnd_entries)
    result = ConversionResult(
        status="success",
        source_path=source_path,
        output_path=None,
        report_path=report_path,
        validation_json_path=validation_json_path,
        row_count=len(draft.mnd_entries),
        total_debit=debit,
        total_credit=credit,
        period=draft.mnd_entries[0].period if draft.mnd_entries else None,
        batch=draft.source_entries[0].batch if draft.source_entries else None,
        entry_date=draft.source_entries[0].entry_date.isoformat() if draft.source_entries else None,
        account_count=len({entry.account for entry in draft.mnd_entries}),
        unknown_account_count=0,
        source_sha256=draft.source_sha256,
        mnd_sha256=draft.mnd_sha256,
        messages=[],
        reconciliations=all_reconciliations,
    )
    _write_artifacts(result, overwrite=overwrite)
    return result


def convert_file(
    source_path: Path,
    output_path: Path,
    config: AppConfig,
    *,
    period: str | None = None,
    overwrite: bool = False,
    report_path: Path | None = None,
    validation_json_path: Path | None = None,
    write_report: bool = True,
    write_validation_json: bool = True,
    reconciliations: list[ReconciliationResult] | None = None,
) -> ConversionResult:
    reconciliations = reconciliations or []
    report_path = (report_path or default_report_path(output_path)) if write_report else None
    validation_json_path = (validation_json_path or default_validation_json_path(output_path)) if write_validation_json else None
    reconciliation_errors = _reconciliation_error_details(reconciliations)
    if reconciliation_errors:
        result = _failed_result(source_path, output_path, report_path, validation_json_path, reconciliation_errors, reconciliations)
        _write_artifacts(result, overwrite=True)
        raise ValidationFailed(reconciliation_errors)
    _assert_output_available(output_path, overwrite=overwrite)

    try:
        draft = build_conversion_draft(source_path, config, period=period)
    except ValidationFailed as error:
        result = _failed_result(source_path, output_path, report_path, validation_json_path, error.errors, reconciliations)
        _write_artifacts(result, overwrite=True)
        raise

    all_reconciliations = [_mnd_source_reconciliation(draft, config.validation.debit_credit_tolerance), *reconciliations]
    mnd_reconciliation_errors = _reconciliation_error_details(all_reconciliations[:1])
    if mnd_reconciliation_errors:
        result = _failed_result(source_path, output_path, report_path, validation_json_path, mnd_reconciliation_errors, all_reconciliations)
        _write_artifacts(result, overwrite=True)
        raise ValidationFailed(mnd_reconciliation_errors)

    debit, credit = mnd_totals(draft.mnd_entries)
    result = ConversionResult(
        status="success",
        source_path=source_path,
        output_path=output_path,
        report_path=report_path,
        validation_json_path=validation_json_path,
        row_count=len(draft.mnd_entries),
        total_debit=debit,
        total_credit=credit,
        period=draft.mnd_entries[0].period if draft.mnd_entries else None,
        batch=draft.source_entries[0].batch if draft.source_entries else None,
        entry_date=draft.source_entries[0].entry_date.isoformat() if draft.source_entries else None,
        account_count=len({entry.account for entry in draft.mnd_entries}),
        unknown_account_count=0,
        source_sha256=draft.source_sha256,
        mnd_sha256=draft.mnd_sha256,
        messages=[],
        reconciliations=all_reconciliations,
    )

    _write_text_atomic(output_path, draft.mnd_text, encoding=config.mnd.output_encoding, overwrite=overwrite)
    _write_artifacts(result, overwrite=True)
    return result


def _failed_result(
    source_path: Path,
    output_path: Path | None,
    report_path: Path | None,
    validation_json_path: Path | None,
    errors: list[ErrorDetail],
    reconciliations: list[ReconciliationResult] | None = None,
) -> ConversionResult:
    source_hash = None
    try:
        if source_path.exists():
            source_hash = _sha256_file(source_path)
    except FileOperationError:
        source_hash = None
    return ConversionResult(
        status="failed",
        source_path=source_path,
        output_path=output_path,
        report_path=report_path,
        validation_json_path=validation_json_path,
        row_count=0,
        total_debit=ZERO,
        total_credit=ZERO,
        period=None,
        batch=None,
        entry_date=None,
        account_count=None,
        unknown_account_count=sum(1 for error in errors if error.code == "account_unknown"),
        source_sha256=source_hash,
        mnd_sha256=None,
        messages=[
            ValidationMessage(
                severity="error",
                code=error.code,
                message=error.message,
                line_number=error.line_number,
                field=error.field,
            )
            for error in errors
        ],
        reconciliations=reconciliations or [],
    )


def _write_artifacts(result: ConversionResult, *, overwrite: bool) -> None:
    if result.report_path:
        _write_text_atomic(result.report_path, build_markdown_report(result), encoding="utf-8", overwrite=overwrite)
    if result.validation_json_path:
        _write_text_atomic(result.validation_json_path, build_validation_json(result), encoding="utf-8", overwrite=overwrite)


def _assert_output_available(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ValidationFailed([ErrorDetail("output_exists", f"Le fichier de sortie existe déjà: {path}")])


def _write_text_atomic(path: Path, text: str, *, encoding: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileOperationError(f"Le fichier existe déjà: {path}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(text, encoding=encoding, newline="")
        os.replace(tmp_path, path)
    except OSError as error:
        raise FileOperationError(f"Impossible d'écrire le fichier: {path}") from error


def _reconciliation_error_details(reconciliations: list[ReconciliationResult]) -> list[ErrorDetail]:
    errors: list[ErrorDetail] = []
    for reconciliation in reconciliations:
        if not reconciliation.required or reconciliation.status != "failed":
            continue
        current = [
            ErrorDetail(message.code, message.message, message.line_number, message.field)
            for message in reconciliation.messages
            if message.severity == "error"
        ]
        errors.extend(current or [ErrorDetail("reconciliation_failed", f"Rapprochement {reconciliation.report_type} en écart.")])
    return errors


def _mnd_source_reconciliation(draft: ConversionDraft, tolerance: Decimal) -> ReconciliationResult:
    source_debit, source_credit = source_totals(draft.source_entries)
    mnd_debit, mnd_credit = mnd_totals(draft.mnd_entries)
    debit_difference = source_debit - mnd_debit
    credit_difference = source_credit - mnd_credit
    ok = abs(debit_difference) <= tolerance and abs(credit_difference) <= tolerance
    messages = []
    if not ok:
        messages.append(
            ValidationMessage(
                "error",
                "mnd_source_total_mismatch",
                f"Les totaux du MND ne concordent pas avec l'écriture: débit={debit_difference:.2f}, crédit={credit_difference:.2f}.",
            )
        )

    source_batches = sorted({entry.batch for entry in draft.source_entries})
    source_periods = sorted({entry.entry_date.strftime("%Y%m") for entry in draft.source_entries})
    mnd_batches = sorted({entry.batch for entry in draft.mnd_entries})
    mnd_periods = sorted({entry.period for entry in draft.mnd_entries})
    return ReconciliationResult(
        report_type="MND",
        status="success" if ok else "failed",
        required=True,
        report_path=None,
        source_debit=source_debit,
        source_credit=source_credit,
        report_debit=mnd_debit,
        report_credit=mnd_credit,
        debit_difference=debit_difference,
        credit_difference=credit_difference,
        tolerance=tolerance,
        debit_label="Total débit MND",
        credit_label="Total crédit MND",
        source_batch=source_batches[0] if len(source_batches) == 1 else None,
        report_batch=mnd_batches[0] if len(mnd_batches) == 1 else None,
        source_period=source_periods[0] if len(source_periods) == 1 else None,
        report_period=mnd_periods[0] if len(mnd_periods) == 1 else None,
        source_dates=tuple(sorted({entry.entry_date.isoformat() for entry in draft.source_entries})),
        report_dates=tuple(sorted({entry.entry_date.isoformat() for entry in draft.mnd_entries})),
        messages=messages,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise FileOperationError(f"Impossible de lire le fichier: {path}") from error
    return digest.hexdigest()

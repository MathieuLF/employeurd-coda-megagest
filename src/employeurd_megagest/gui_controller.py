from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import load_app_config
from .converter import convert_file, validate_file
from .errors import ValidationFailed
from .models import ConversionResult, ReconciliationResult
from .audit_log import write_audit_event
from .output_plan import OutputPlan, build_output_plan
from .parser_employeurd import parse_employeurd_file
from .reconciliation import reconcile_spd640, reconciliation_failed
from .resource_paths import default_config_dir
from .validator import validate_source_entries


@dataclass(frozen=True)
class GuiOperationResult:
    ok: bool
    message: str
    conversion: ConversionResult | None = None
    output_plan: OutputPlan | None = None
    reconciliations: list[ReconciliationResult] = field(default_factory=list)


class GuiController:
    def __init__(self, *, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or default_config_dir()
        self.last_validation: GuiOperationResult | None = None

    def validate(
        self,
        *,
        source_path: Path,
        spd640_path: Path | None,
        require_spd640: bool,
    ) -> GuiOperationResult:
        config = load_app_config(self.config_dir)
        entries = parse_employeurd_file(source_path, reject_non_crlf=config.validation.reject_non_crlf_source)
        validate_source_entries(entries, config.validation)
        reconciliations = _build_reconciliations(entries, spd640_path, config, require_spd640)
        _raise_if_required_reconciliation_failed(reconciliations)
        result = validate_file(source_path, config, reconciliations=reconciliations)
        operation = GuiOperationResult(
            ok=True,
            message=f"Validation réussie - {result.row_count} lignes - débit {result.total_debit:.2f} / crédit {result.total_credit:.2f}",
            conversion=result,
            reconciliations=reconciliations,
        )
        _audit(config, "gui_validate", "success", {"row_count": result.row_count, "reconciliations": len(reconciliations)})
        self.last_validation = operation
        return operation

    def generate(
        self,
        *,
        source_path: Path,
        output_root: Path,
        spd640_path: Path | None,
        require_spd640: bool,
        write_report: bool,
        write_validation_json: bool,
    ) -> GuiOperationResult:
        config = load_app_config(self.config_dir)
        entries = parse_employeurd_file(source_path, reject_non_crlf=config.validation.reject_non_crlf_source)
        validate_source_entries(entries, config.validation)
        reconciliations = _build_reconciliations(entries, spd640_path, config, require_spd640)
        _raise_if_required_reconciliation_failed(reconciliations)
        output_plan = build_output_plan(
            source_path,
            output_root,
            include_report=write_report,
            include_validation_json=write_validation_json,
        )
        result = convert_file(
            source_path,
            output_plan.mnd_path,
            config,
            overwrite=False,
            report_path=output_plan.report_path,
            validation_json_path=output_plan.validation_json_path,
            write_report=write_report,
            write_validation_json=write_validation_json,
            reconciliations=reconciliations,
        )
        operation = GuiOperationResult(
            ok=True,
            message=f"MND généré : {result.output_path}",
            conversion=result,
            output_plan=output_plan,
            reconciliations=reconciliations,
        )
        _audit(
            config,
            "gui_generate",
            "success",
            {
                "row_count": result.row_count,
                "reconciliations": len(reconciliations),
                "write_report": write_report,
                "write_validation_json": write_validation_json,
            },
        )
        self.last_validation = operation
        return operation


def _build_reconciliations(entries, spd640_path: Path | None, config, require_spd640: bool) -> list[ReconciliationResult]:
    if not spd640_path:
        if require_spd640:
            raise ValidationFailed("Le rapport SPD640-P est requis en mode bloquant.")
        return []
    return [reconcile_spd640(entries, spd640_path, config, required=require_spd640 or None)]


def _raise_if_required_reconciliation_failed(reconciliations: list[ReconciliationResult]) -> None:
    for reconciliation in reconciliations:
        if reconciliation_failed(reconciliation):
            raise ValidationFailed(
                f"Rapprochement {reconciliation.report_type} en écart: débit={reconciliation.debit_difference:.2f}, crédit={reconciliation.credit_difference:.2f}."
            )


def _audit(config, event: str, status: str, details: dict) -> None:
    audit_config = getattr(config, "audit_log", {})
    if not audit_config.get("enabled", False):
        return
    log_dir = Path(audit_config["directory"]) if audit_config.get("directory") else None
    try:
        write_audit_event(event, status=status, details=details, log_dir=log_dir)
    except OSError:
        pass

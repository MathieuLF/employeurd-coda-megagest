from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .models import ConversionResult, ReconciliationResult, ValidationMessage
from .output_plan import build_output_plan
from .parser_employeurd import parse_employeurd_file


MONEY_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class FilePreview:
    path: Path | None
    title: str
    detail: str
    status: str
    ok: bool


@dataclass(frozen=True)
class OutputPreview:
    directory: Path | None
    files: tuple[str, ...] = ()
    detail: str = ""
    ok: bool = False


@dataclass(frozen=True)
class ResultMetric:
    label: str
    value: str


@dataclass(frozen=True)
class GuiViewState:
    input_file_path: Path | None
    spd640_path: Path | None
    output_dir: Path | None
    validation_result: ConversionResult | None = None
    last_generated_files: tuple[Path, ...] = ()
    update_status: str = "Non vérifiée"
    strict_spd640_enabled: bool = False
    busy: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def can_validate(self) -> bool:
        return bool(self.input_file_path and self.output_dir and not self.busy and not self.errors)

    @property
    def validation_ok(self) -> bool:
        return bool(self.validation_result and self.validation_result.status == "success" and not self.errors)

    @property
    def can_generate(self) -> bool:
        return self.can_validate and self.validation_ok


def build_file_preview(value: str, *, label: str, suffixes: tuple[str, ...], optional: bool = False) -> FilePreview:
    if not value.strip():
        status = "Facultatif" if optional else "Obligatoire"
        detail = f"{label}: aucun fichier sélectionné." if optional else f"{label}: ajoutez le fichier à convertir."
        return FilePreview(None, status, detail, "warning" if not optional else "info", optional)

    path = Path(value)
    if not path.exists():
        return FilePreview(path, "Introuvable", f"{label}: le fichier n'existe pas.", "error", False)
    if not path.is_file():
        return FilePreview(path, "Invalide", f"{label}: le chemin sélectionné n'est pas un fichier.", "error", False)
    if suffixes and path.suffix.lower() not in suffixes:
        return FilePreview(path, "Format à vérifier", f"{path.name} - extension inattendue.", "warning", optional)

    stat = path.stat()
    detail = f"{path.name} - {_format_size(stat.st_size)} - modifié le {_format_datetime(stat.st_mtime)}"
    return FilePreview(path, "Prêt", detail, "success", True)


def default_output_root() -> Path:
    documents = Path.home() / "Documents"
    return documents if documents.exists() else Path.home()


def build_output_preview(
    source_value: str,
    output_value: str,
    *,
    include_report: bool = True,
    include_validation_json: bool = True,
) -> OutputPreview:
    using_default = not output_value.strip()
    output_dir = default_output_root() if using_default else Path(output_value)
    if output_dir.exists() and not output_dir.is_dir():
        return OutputPreview(output_dir, detail="Le chemin de sortie existe mais n'est pas un dossier.", ok=False)

    writable = _directory_probably_writable(output_dir)
    if not writable:
        return OutputPreview(output_dir, detail="Le dossier de sortie ne semble pas accessible en écriture.", ok=False)

    source_path = Path(source_value) if source_value.strip() else Path("EmployeurD.txt")
    entry_date, batch = _source_identity(source_path)
    plan = build_output_plan(
        source_path,
        output_dir,
        entry_date=entry_date,
        batch=batch,
        include_report=include_report,
        include_validation_json=include_validation_json,
    )
    files = tuple(
        path.name
        for path in (plan.mnd_path, plan.report_path, plan.validation_json_path)
        if path is not None
    )
    prefix = f"Sortie par défaut : {output_dir}" if using_default else f"Sortie choisie : {output_dir}"
    detail = f"{prefix}\nSous-dossier horodaté : {plan.directory.name}"
    return OutputPreview(plan.directory, files=files, detail=detail, ok=True)


def build_metrics(
    result: ConversionResult | None,
    reconciliations: list[ReconciliationResult] | None = None,
    *,
    include_mnd_recheck: bool = True,
) -> list[ResultMetric]:
    if not result:
        return [
            ResultMetric("Fichiers", "En attente de vérification"),
            ResultMetric("MND", "Créé après une vérification réussie"),
            ResultMetric("SPD640-P", "Facultatif, utile pour confirmer les totaux débit/crédit"),
        ]

    delta = abs(result.total_debit - result.total_credit)
    metrics = [
        ResultMetric("Lignes source", str(result.row_count)),
        ResultMetric("Lot", result.batch or "n/d"),
        ResultMetric("Date", result.entry_date or "n/d"),
        ResultMetric("Période", result.period or "n/d"),
        ResultMetric("Débits", _format_money(result.total_debit)),
        ResultMetric("Crédits", _format_money(result.total_credit)),
        ResultMetric("Écart", _format_money(delta)),
        ResultMetric("Comptes uniques", str(result.account_count) if result.account_count is not None else "n/d"),
        ResultMetric("Comptes au débit", str(result.debit_account_count) if result.debit_account_count is not None else "n/d"),
        ResultMetric("Comptes au crédit", str(result.credit_account_count) if result.credit_account_count is not None else "n/d"),
    ]
    if include_mnd_recheck:
        metrics.append(ResultMetric("Relecture MND", "OK" if result.status == "success" else "Échec"))

    current_reconciliations = reconciliations if reconciliations is not None else result.reconciliations
    if current_reconciliations:
        for reconciliation in current_reconciliations:
            metrics.extend(_reconciliation_metrics(reconciliation))
    else:
        metrics.append(ResultMetric("SPD640-P", "Non fourni / optionnel"))
    return metrics


def blocking_messages(result: ConversionResult | None, errors: tuple[str, ...] = ()) -> list[str]:
    messages = list(errors)
    if result:
        messages.extend(_message_to_text(message) for message in result.messages if message.severity == "error")
    return messages


def summary_text(
    result: ConversionResult | None,
    reconciliations: list[ReconciliationResult] | None = None,
    *,
    include_mnd_recheck: bool = True,
) -> str:
    lines = [
        f"{metric.label}: {metric.value}"
        for metric in build_metrics(result, reconciliations, include_mnd_recheck=include_mnd_recheck)
    ]
    return "\n".join(lines)


def generated_files(result: ConversionResult | None) -> tuple[Path, ...]:
    if not result:
        return ()
    paths = [result.output_path, result.report_path, result.validation_json_path]
    return tuple(path for path in paths if path)


def _directory_probably_writable(path: Path) -> bool:
    target = path if path.exists() else path.parent
    if not target:
        return False
    if not target.exists():
        return False
    return os.access(target, os.W_OK)


def _source_identity(path: Path):
    if not path.exists() or not path.is_file():
        return None, None
    try:
        entries = parse_employeurd_file(path)
    except Exception:
        return None, None
    if not entries:
        return None, None
    return entries[0].entry_date, entries[0].batch


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} o"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} Ko"
    return f"{size / (1024 * 1024):.1f} Mo"


def _format_datetime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _format_money(value: Decimal) -> str:
    return f"{value:,.2f} $".replace(",", " ").replace(".", ",")


def _reconciliation_metrics(reconciliation: ReconciliationResult) -> list[ResultMetric]:
    status = "concordant" if reconciliation.status == "success" else "en écart"
    if reconciliation.report_type == "SPD640":
        return [
            ResultMetric(
                "SPD640-P",
                f"{status.capitalize()} - totaux comparés débit {_format_money(reconciliation.report_debit)} / crédit {_format_money(reconciliation.report_credit)}",
            ),
            ResultMetric(
                "Écart SPD640-P",
                f"débit {_format_money(reconciliation.debit_difference)} / crédit {_format_money(reconciliation.credit_difference)}",
            ),
        ]
    return [
        ResultMetric(
            reconciliation.report_type,
            f"{status.capitalize()} - écarts débit {_format_money(reconciliation.debit_difference)} / crédit {_format_money(reconciliation.credit_difference)}",
        )
    ]


def _unknown_account_count(messages: list[ValidationMessage]) -> str:
    count = sum(1 for message in messages if message.code == "account_unknown")
    return str(count)


def _message_to_text(message: ValidationMessage) -> str:
    prefix = f"Ligne {message.line_number}: " if message.line_number else ""
    return prefix + message.message

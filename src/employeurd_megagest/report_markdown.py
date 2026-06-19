from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .models import ConversionResult, ValidationMessage
from .version import __version__


def build_markdown_report(result: ConversionResult) -> str:
    lines = [
        "# Rapport de conversion EmployeurD vers MégaGest",
        "",
        f"Statut: **{_status_label(result.status)}**",
        f"Version: `{__version__}`",
        f"Généré le: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## Fichiers",
        "",
        f"- Source: `{result.source_path}`",
        f"- Sortie MND: `{result.output_path}`" if result.output_path else "- Sortie MND: non générée",
        f"- Rapport: `{result.report_path}`" if result.report_path else "- Rapport: non écrit",
        f"- JSON validation: `{result.validation_json_path}`" if result.validation_json_path else "- JSON validation: non écrit",
        "",
        "## Synthèse",
        "",
        f"- Lignes: {result.row_count}",
        f"- Débit: {_money(result.total_debit)}",
        f"- Crédit: {_money(result.total_credit)}",
        f"- Écart: {_money(abs(result.total_debit - result.total_credit))}",
        f"- Période: {result.period or 'n/d'}",
        f"- Date d'écriture: {result.entry_date or 'n/d'}",
        f"- Lot: {result.batch or 'n/d'}",
        f"- Comptes détectés: {result.account_count if result.account_count is not None else 'n/d'}",
        "",
        "## Empreintes",
        "",
        f"- SHA256 source: `{result.source_sha256 or 'n/d'}`",
        f"- SHA256 MND: `{result.mnd_sha256 or 'n/d'}`",
        "",
        "## Messages",
        "",
    ]

    if result.messages:
        lines.extend(_format_message(message) for message in result.messages)
    else:
        lines.append("- Aucun message bloquant.")

    lines.extend(["", "## Rapprochements", ""])
    if result.reconciliations:
        for reconciliation in result.reconciliations:
            lines.extend(
                [
                    f"### {reconciliation.report_type}",
                    "",
                    f"- Statut: {_reconciliation_status(reconciliation.status)}",
                    f"- Obligatoire: {'oui' if reconciliation.required else 'non'}",
                    f"- Rapport: `{reconciliation.report_path}`" if reconciliation.report_path else "- Rapport: n/d",
                    f"- Lot source: {reconciliation.source_batch or 'n/d'}",
                    f"- Lot comparé: {reconciliation.report_batch or 'n/d'}",
                    f"- Période source: {reconciliation.source_period or 'n/d'}",
                    f"- Période comparée: {reconciliation.report_period or 'n/d'}",
                    f"- Débit source: {_money(reconciliation.source_debit)}",
                    f"- Débit comparé: {_money(reconciliation.report_debit)}",
                    f"- Écart débit: {_money(reconciliation.debit_difference)}",
                    f"- Crédit source: {_money(reconciliation.source_credit)}",
                    f"- Crédit comparé: {_money(reconciliation.report_credit)}",
                    f"- Écart crédit: {_money(reconciliation.credit_difference)}",
                    f"- Formule débit: {reconciliation.debit_label}",
                    f"- Formule crédit: {reconciliation.credit_label}",
                    "",
                ]
            )
            if reconciliation.messages:
                lines.extend(_format_message(message) for message in reconciliation.messages)
                lines.append("")
    else:
        lines.append("- Aucun rapprochement fourni.")

    lines.extend(
        [
            "",
            "## Confidentialité",
            "",
            "Le rapport ne contient pas le contenu détaillé du fichier de paie. Les contrôles reposent sur des totaux, des comptes et des empreintes locales.",
            "",
        ]
    )
    return "\n".join(lines)


def _status_label(status: str) -> str:
    return "SUCCÈS" if status == "success" else "ÉCHEC"


def _reconciliation_status(status: str) -> str:
    labels = {"success": "OK", "failed": "ÉCART", "skipped": "IGNORÉ"}
    return labels.get(status, status)


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _format_message(message: ValidationMessage) -> str:
    parts = [message.severity.upper(), message.code]
    if message.line_number is not None:
        parts.append(f"ligne {message.line_number}")
    if message.field:
        parts.append(message.field)
    return f"- {' / '.join(parts)}: {message.message}"


def default_report_path(output_path: Path) -> Path:
    return output_path.with_suffix(".rapport.md")

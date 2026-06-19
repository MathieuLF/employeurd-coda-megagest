from __future__ import annotations

from .errors import ErrorDetail, ValidationFailed


FRIENDLY_MESSAGES = {
    "output_exists": "Un fichier de sortie existe déjà. Choisissez un autre dossier ou confirmez le remplacement.",
    "source_unbalanced": "Les écritures EmployeurD ne sont pas équilibrées.",
    "account_unknown": "Un compte MégaGest n'est pas autorisé par la configuration.",
    "source_line_length": "Une ligne du fichier EmployeurD n'a pas la longueur attendue de 77 caractères.",
    "source_amount_format": "Un montant du fichier EmployeurD est invalide. Il doit être numérique avec au plus deux décimales.",
    "source_date_invalid": "Une date du fichier EmployeurD est invalide.",
    "spd640_amount_mismatch": "Le rapport SPD640-P ne concorde pas avec les totaux du fichier EmployeurD.",
    "spd640_batch_mismatch": "Le lot du rapport SPD640-P ne correspond pas au lot du fichier EmployeurD.",
    "spd640_period_mismatch": "La période du rapport SPD640-P ne correspond pas à la période du fichier EmployeurD.",
    "validation_failed": "La validation ne peut pas continuer avec les options actuelles.",
}


def friendly_error_message(error: Exception) -> str:
    if isinstance(error, ValidationFailed):
        return "\n".join(_friendly_detail(detail) for detail in error.errors)
    return str(error)


def technical_error_message(error: Exception) -> str:
    if isinstance(error, ValidationFailed):
        return "\n".join(f"- {detail.format()}" for detail in error.errors)
    return str(error)


def _friendly_detail(detail: ErrorDetail) -> str:
    message = FRIENDLY_MESSAGES.get(detail.code, detail.message)
    location = f" Ligne {detail.line_number}." if detail.line_number is not None else ""
    return f"- {message}{location}"

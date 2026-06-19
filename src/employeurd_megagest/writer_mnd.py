from __future__ import annotations

from decimal import Decimal

from .errors import ValidationFailed
from .models import MndEntry


MND_LINE_LENGTH = 479
CENT = Decimal("0.01")


def format_amount(value: Decimal) -> str:
    if value < 0:
        raise ValidationFailed("Un montant MND ne peut pas être négatif.")
    if value != value.quantize(CENT):
        raise ValidationFailed("Un montant MND ne peut pas dépasser 2 décimales.")
    formatted = f"{value:013.2f}"
    if len(formatted) != 13:
        raise ValidationFailed("Montant trop grand pour le champ MND de 13 caractères.")
    return formatted


def build_mnd_line(entry: MndEntry) -> str:
    _require_exact_digits(entry.account, 10, "compte MND")
    _require_exact_digits(entry.period, 6, "période MND")
    _require_exact_digits(entry.batch, 6, "batch MND")
    _require_fits(entry.reference, 10, "référence MND")
    _require_fits(entry.source_label, 50, "source MND")
    _require_fits(entry.extra, 115, "champ auxiliaire MND")

    date_text = entry.entry_date.strftime("%Y%m%d")
    date2_text = entry.date2.strftime("%Y%m%d")

    line = (
        "P"
        + entry.account
        + " " * 5
        + entry.period
        + " " * 30
        + entry.reference.ljust(10)
        + date_text
        + entry.source_label.ljust(50)
        + entry.extra.ljust(115)
        + format_amount(entry.debit)
        + " "
        + format_amount(entry.credit)
        + " "
        + entry.batch
        + " " * 4
        + date2_text
        + " " * 198
    )
    if len(line) != MND_LINE_LENGTH:
        raise ValidationFailed(f"Longueur MND invalide: {len(line)}.")
    return line


def write_mnd_text(entries: list[MndEntry]) -> str:
    if not entries:
        raise ValidationFailed("Aucune ligne MND à écrire.")
    return "".join(build_mnd_line(entry) + "\r\n" for entry in entries)


def _require_exact_digits(value: str, width: int, field_name: str) -> None:
    if len(value) != width or not value.isdigit():
        raise ValidationFailed(f"{field_name} doit contenir exactement {width} chiffres.")


def _require_fits(value: str, width: int, field_name: str) -> None:
    if len(value) > width:
        raise ValidationFailed(f"{field_name} dépasse {width} caractères.")

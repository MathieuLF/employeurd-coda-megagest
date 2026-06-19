from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import ErrorDetail, FileOperationError, ValidationFailed
from .models import MndEntry
from .writer_mnd import MND_LINE_LENGTH


MND_AMOUNT_PATTERN = re.compile(r"^\d{10}\.\d{2}$")


def parse_mnd_file(path: Path, *, require_crlf: bool = True, encoding: str = "cp1252") -> list[MndEntry]:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise FileOperationError(f"Impossible de lire le fichier MND: {path}") from error

    try:
        text = content.decode(encoding)
    except UnicodeDecodeError as error:
        raise ValidationFailed(f"Fichier MND non décodable en {encoding}.") from error
    return parse_mnd_text(text, require_crlf=require_crlf)


def parse_mnd_text(text: str, *, require_crlf: bool = True) -> list[MndEntry]:
    if not text:
        raise ValidationFailed("Le fichier MND est vide.")
    if require_crlf:
        normalized = text.replace("\r\n", "")
        if "\r" in normalized or "\n" in normalized:
            raise ValidationFailed("Les fins de ligne MND doivent être CRLF.")

    if "\r\n" in text:
        lines = text.split("\r\n")
    else:
        lines = text.splitlines()
    if lines and lines[-1] == "":
        lines = lines[:-1]

    entries: list[MndEntry] = []
    errors: list[ErrorDetail] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            entries.append(parse_mnd_line(line, line_number))
        except ValidationFailed as error:
            errors.extend(error.errors)
    if errors:
        raise ValidationFailed(errors)
    if not entries:
        raise ValidationFailed("Le fichier MND ne contient aucune ligne.")
    return entries


def parse_mnd_line(line: str, line_number: int = 1) -> MndEntry:
    errors: list[ErrorDetail] = []
    if len(line) != MND_LINE_LENGTH:
        raise ValidationFailed(
            [ErrorDetail("mnd_line_length", f"Longueur attendue {MND_LINE_LENGTH}, reçue {len(line)}.", line_number)]
        )

    record_type = line[0:1]
    account = line[1:11]
    period = line[16:22]
    reference = line[52:62].rstrip()
    date_text = line[62:70]
    source_label = line[70:120].rstrip()
    extra = line[120:235].rstrip()
    debit_text = line[235:248]
    credit_text = line[249:262]
    batch = line[263:269]
    date2_text = line[273:281]

    if record_type != "P":
        errors.append(ErrorDetail("mnd_record_type", "Le type d'enregistrement doit être P.", line_number))
    for start, end, code in [(11, 16, "mnd_spaces_11_16"), (22, 52, "mnd_spaces_22_52"), (248, 249, "mnd_space_249"), (262, 263, "mnd_space_263"), (269, 273, "mnd_spaces_270_273"), (281, 479, "mnd_trailing_spaces")]:
        if line[start:end] != " " * (end - start):
            errors.append(ErrorDetail(code, "Des espaces fixes sont attendus dans ce champ.", line_number))
    if len(account) != 10 or not account.isdigit():
        errors.append(ErrorDetail("mnd_account", "Le compte MND doit contenir 10 chiffres.", line_number, "account"))
    if len(period) != 6 or not period.isdigit():
        errors.append(ErrorDetail("mnd_period", "La période doit contenir 6 chiffres.", line_number, "period"))
    if len(batch) != 6 or not batch.isdigit():
        errors.append(ErrorDetail("mnd_batch", "Le batch MND doit contenir 6 chiffres.", line_number, "batch"))

    entry_date = _parse_date(date_text, "date", line_number, errors)
    date2 = _parse_date(date2_text, "date2", line_number, errors)
    debit = _parse_amount(debit_text, "debit", line_number, errors)
    credit = _parse_amount(credit_text, "credit", line_number, errors)

    if debit is not None and credit is not None and debit > 0 and credit > 0:
        errors.append(ErrorDetail("mnd_amount_side", "Débit et crédit ne peuvent pas être actifs ensemble.", line_number))

    if errors:
        raise ValidationFailed(errors)

    assert entry_date is not None
    assert date2 is not None
    assert debit is not None
    assert credit is not None
    return MndEntry(
        line_number=line_number,
        account=account,
        period=period,
        reference=reference,
        entry_date=entry_date,
        source_label=source_label,
        extra=extra,
        debit=debit,
        credit=credit,
        batch=batch,
        date2=date2,
    )


def _parse_date(value: str, field: str, line_number: int, errors: list[ErrorDetail]):
    if len(value) != 8 or not value.isdigit():
        errors.append(ErrorDetail("mnd_date_format", "La date doit être AAAAMMJJ.", line_number, field))
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        errors.append(ErrorDetail("mnd_date_invalid", "La date est invalide.", line_number, field))
        return None


def _parse_amount(value: str, field: str, line_number: int, errors: list[ErrorDetail]) -> Decimal | None:
    if not MND_AMOUNT_PATTERN.fullmatch(value):
        errors.append(ErrorDetail("mnd_amount_format", "Le montant MND doit avoir le format 0000000000.00.", line_number, field))
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        errors.append(ErrorDetail("mnd_amount_decimal", "Le montant MND n'est pas un nombre décimal valide.", line_number, field))
        return None

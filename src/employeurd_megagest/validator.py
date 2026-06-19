from __future__ import annotations

from decimal import Decimal

from .config import AccountConfig, MndConfig, ValidationConfig
from .errors import ErrorDetail, ValidationFailed
from .models import EmployeurDEntry, MndEntry


ZERO = Decimal("0.00")


def source_totals(entries: list[EmployeurDEntry]) -> tuple[Decimal, Decimal]:
    debit = sum((entry.amount for entry in entries if entry.amount > 0), ZERO)
    credit = sum((-entry.amount for entry in entries if entry.amount < 0), ZERO)
    return debit, credit


def mnd_totals(entries: list[MndEntry]) -> tuple[Decimal, Decimal]:
    debit = sum((entry.debit for entry in entries), ZERO)
    credit = sum((entry.credit for entry in entries), ZERO)
    return debit, credit


def validate_source_entries(entries: list[EmployeurDEntry], config: ValidationConfig) -> None:
    errors: list[ErrorDetail] = []
    if not entries:
        raise ValidationFailed("Le fichier source ne contient aucune écriture.")

    if config.require_single_batch and len({entry.batch for entry in entries}) != 1:
        errors.append(ErrorDetail("source_multiple_batches", "Plusieurs lots sont présents sans mode multi-lot."))
    if config.require_single_date and len({entry.entry_date for entry in entries}) != 1:
        errors.append(ErrorDetail("source_multiple_dates", "Plusieurs dates sont présentes sans mode multi-date."))
    if config.reject_zero_amount_lines:
        for entry in entries:
            if entry.amount == ZERO:
                errors.append(ErrorDetail("source_zero_amount", "Montant zéro interdit.", entry.line_number, "amount"))

    debit, credit = source_totals(entries)
    delta = abs(debit - credit)
    if config.require_balanced and delta > config.debit_credit_tolerance:
        errors.append(
            ErrorDetail(
                "source_unbalanced",
                f"Écritures non balancées: débit={debit:.2f}, crédit={credit:.2f}, écart={delta:.2f}.",
            )
        )

    if errors:
        raise ValidationFailed(errors)


def convert_account(source_account: str, account_config: AccountConfig) -> str:
    explicit = (account_config.source_to_mnd or {}).get(source_account)
    if explicit:
        return explicit
    if account_config.conversion_strategy == "drop_first_digit":
        if len(source_account) != 11 or not source_account.isdigit():
            raise ValidationFailed("Le compte source doit contenir 11 chiffres.")
        return source_account[1:]
    raise ValidationFailed(f"Stratégie de conversion de compte inconnue: {account_config.conversion_strategy}")


def convert_to_mnd_entries(
    entries: list[EmployeurDEntry],
    *,
    account_config: AccountConfig,
    mnd_config: MndConfig,
    validation_config: ValidationConfig,
    period_override: str | None = None,
) -> list[MndEntry]:
    converted: list[MndEntry] = []
    errors: list[ErrorDetail] = []

    for entry in entries:
        try:
            account = convert_account(entry.account, account_config)
        except ValidationFailed as error:
            errors.extend(
                ErrorDetail(detail.code, detail.message, entry.line_number, "account") for detail in error.errors
            )
            continue

        if validation_config.reject_unknown_accounts and account not in account_config.allowed_accounts:
            errors.append(ErrorDetail("account_unknown", f"Compte MégaGest non autorisé: {account}", entry.line_number, "account"))
            continue

        period = period_override or entry.entry_date.strftime("%Y%m")
        if len(period) != 6 or not period.isdigit():
            errors.append(ErrorDetail("period_invalid", "La période doit être AAAAMM.", entry.line_number, "period"))
            continue

        debit = entry.amount if entry.amount > 0 else ZERO
        credit = -entry.amount if entry.amount < 0 else ZERO
        converted.append(
            MndEntry(
                line_number=entry.line_number,
                account=account,
                period=period,
                reference=_build_reference(entry.batch, mnd_config),
                entry_date=entry.entry_date,
                source_label=mnd_config.source_label,
                extra=_build_extra(mnd_config),
                debit=debit,
                credit=credit,
                batch=_build_mnd_batch(entry.batch, mnd_config),
                date2=entry.entry_date,
                source_account=entry.account,
            )
        )

    if errors:
        raise ValidationFailed(errors)
    return converted


def validate_mnd_entries(entries: list[MndEntry], config: ValidationConfig) -> None:
    errors: list[ErrorDetail] = []
    if not entries:
        raise ValidationFailed("Aucune ligne MND générée.")

    for entry in entries:
        if entry.debit < 0 or entry.credit < 0:
            errors.append(ErrorDetail("mnd_negative_amount", "Débit ou crédit MND négatif interdit.", entry.line_number))
        if entry.debit > 0 and entry.credit > 0:
            errors.append(ErrorDetail("mnd_amount_side", "Une seule colonne monétaire doit être active.", entry.line_number))
        if entry.debit == ZERO and entry.credit == ZERO and config.reject_zero_amount_lines:
            errors.append(ErrorDetail("mnd_zero_amount", "Ligne MND à montant zéro interdite.", entry.line_number))

    debit, credit = mnd_totals(entries)
    delta = abs(debit - credit)
    if config.require_balanced and delta > config.debit_credit_tolerance:
        errors.append(ErrorDetail("mnd_unbalanced", f"MND non balancé: débit={debit:.2f}, crédit={credit:.2f}."))

    if errors:
        raise ValidationFailed(errors)


def compare_roundtrip(expected: list[MndEntry], parsed: list[MndEntry]) -> None:
    errors: list[ErrorDetail] = []
    if len(expected) != len(parsed):
        errors.append(ErrorDetail("roundtrip_count", f"Lignes attendues={len(expected)}, relues={len(parsed)}."))
        raise ValidationFailed(errors)

    fields = ["account", "period", "reference", "entry_date", "source_label", "extra", "debit", "credit", "batch", "date2"]
    for expected_entry, parsed_entry in zip(expected, parsed, strict=True):
        for field_name in fields:
            if getattr(expected_entry, field_name) != getattr(parsed_entry, field_name):
                errors.append(
                    ErrorDetail(
                        "roundtrip_mismatch",
                        f"{field_name}: attendu={getattr(expected_entry, field_name)!r}, relu={getattr(parsed_entry, field_name)!r}.",
                        expected_entry.line_number,
                        field_name,
                    )
                )

    if errors:
        raise ValidationFailed(errors)


def _build_reference(batch: str, config: MndConfig) -> str:
    if config.reference_strategy == "employeurd_batch_full":
        return batch
    raise ValidationFailed(f"Stratégie de référence inconnue: {config.reference_strategy}")


def _build_mnd_batch(batch: str, config: MndConfig) -> str:
    if config.batch_strategy == "employeurd_batch_last_6_digits":
        stripped = batch.lstrip("0") or "0"
        return stripped[-6:].rjust(6, "0")
    raise ValidationFailed(f"Stratégie de lot inconnue: {config.batch_strategy}")


def _build_extra(config: MndConfig) -> str:
    if config.extra_field_strategy == "blank":
        return ""
    raise ValidationFailed(f"Stratégie de champ auxiliaire inconnue: {config.extra_field_strategy}")

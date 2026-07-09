from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from employeurd_megagest.errors import ErrorDetail, FileOperationError, ValidationFailed
from employeurd_megagest.models import PayrollReportTotals


Side = Literal["debit", "credit"]
ZERO = Decimal("0.00")
CENT = Decimal("0.01")
ACCOUNT_PATTERN = re.compile(r"^\d{10}$")
MONEY_PATTERN = re.compile(r"^-?\d+(?:[,.]\d{2})$")
DATE_PATTERN = re.compile(r"Date d['’](?:é|e)criture\s*:\s*(\d{4})/(\d{2})/(\d{2})", re.IGNORECASE)
COMPANY_PATTERN = re.compile(r"Compagnie\s*:\s*(\d+)", re.IGNORECASE)
PC_PATTERN = re.compile(r"\bPC\s*:\s*(\d+)", re.IGNORECASE)
PAYROLL_PERIOD_PATTERN = re.compile(r"P(?:é|e)riode de paie\s*:\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class GLDetailEntry:
    page_number: int
    line_number: int
    account: str
    amount: Decimal
    side: Side
    description: str


@dataclass(frozen=True)
class GLDetailReport:
    source_file: Path
    row_count: int
    accounting_date: date | None
    company: str | None
    accounting_period: str | None
    payroll_period: str | None
    entries: tuple[GLDetailEntry, ...]
    debit_total: Decimal
    credit_total: Decimal
    account_side_totals: dict[tuple[str, Side], Decimal]
    subtotal_count: int
    total_company_debit: Decimal | None = None
    total_company_credit: Decimal | None = None
    total_period_debit: Decimal | None = None
    total_period_credit: Decimal | None = None

    @property
    def period(self) -> str | None:
        return self.accounting_date.strftime("%Y%m") if self.accounting_date else None

    def to_payroll_totals(self) -> PayrollReportTotals:
        return PayrollReportTotals(
            report_type="GL_DETAIL",
            source_file=self.source_file,
            period=self.period,
            pay_date=self.accounting_date,
            batch=None,
            gross_pay=None,
            net_pay=None,
            employee_deductions=None,
            employer_contributions=None,
            vacation_pay=None,
            other_totals={
                "debit": self.debit_total,
                "credit": self.credit_total,
            },
        )


class GLDetailPDFParser:
    report_type = "GL_DETAIL"

    def parse(self, path: Path) -> PayrollReportTotals:
        return parse_gl_detail_pdf(path).to_payroll_totals()


def parse_gl_detail_pdf(path: Path) -> GLDetailReport:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except ModuleNotFoundError as error:
        raise FileOperationError("Le module pdfplumber est requis pour lire le rapport GL PDF.") from error

    entries: list[GLDetailEntry] = []
    errors: list[ErrorDetail] = []
    account_side_totals: defaultdict[tuple[str, Side], Decimal] = defaultdict(lambda: ZERO)
    debit_total = ZERO
    credit_total = ZERO
    subtotal_count = 0
    current_debit = ZERO
    current_credit = ZERO
    total_company_debit: Decimal | None = None
    total_company_credit: Decimal | None = None
    total_period_debit: Decimal | None = None
    total_period_credit: Decimal | None = None
    debit_x: float | None = None
    credit_x: float | None = None
    metadata_text: list[str] = []

    try:
        with pdfplumber.open(path) as document:
            for page_number, page in enumerate(document.pages, start=1):
                page_text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                metadata_text.append(page_text)
                words = page.extract_words(x_tolerance=1, y_tolerance=3, keep_blank_chars=False)
                for line_number, line_words in enumerate(_group_words_by_line(words), start=1):
                    header = _header_columns(line_words)
                    if header:
                        debit_x, credit_x = header
                        continue
                    if debit_x is None or credit_x is None:
                        continue

                    line_text = " ".join(word["text"] for word in line_words)
                    account_word = _find_account_word(line_words)
                    if account_word:
                        amount_word = _find_amount_word(line_words, min(debit_x, credit_x))
                        if amount_word is None:
                            errors.append(
                                ErrorDetail(
                                    "gl_detail_missing_amount",
                                    f"Montant introuvable pour le compte {account_word['text']}.",
                                    page_number,
                                )
                            )
                            continue
                        amount = _parse_decimal(amount_word["text"], errors, page_number, "amount")
                        if amount is None:
                            continue
                        side = _word_side(amount_word, debit_x, credit_x)
                        account = str(account_word["text"])
                        description = _description_for_line(line_words, account_word, amount_word)
                        entries.append(
                            GLDetailEntry(
                                page_number=page_number,
                                line_number=line_number,
                                account=account,
                                amount=amount,
                                side=side,
                                description=description,
                            )
                        )
                        account_side_totals[(account, side)] += amount
                        if side == "debit":
                            debit_total += amount
                            current_debit += amount
                        else:
                            credit_total += amount
                            current_credit += amount
                        continue

                    if line_text.startswith("Sous-total"):
                        subtotal_count += 1
                        amounts = _amounts_by_side(line_words, debit_x, credit_x)
                        expected_debit = amounts.get("debit", ZERO)
                        expected_credit = amounts.get("credit", ZERO)
                        if expected_debit != current_debit or expected_credit != current_credit:
                            errors.append(
                                ErrorDetail(
                                    "gl_detail_subtotal_mismatch",
                                    (
                                        "Sous-total GL incohérent: "
                                        f"débit lu={current_debit:.2f}/attendu={expected_debit:.2f}, "
                                        f"crédit lu={current_credit:.2f}/attendu={expected_credit:.2f}."
                                    ),
                                    page_number,
                                )
                            )
                        current_debit = ZERO
                        current_credit = ZERO
                        continue

                    if line_text.startswith("Total "):
                        amounts = _amounts_by_side(line_words, debit_x, credit_x)
                        if "période comptable" in line_text:
                            total_period_debit = amounts.get("debit", ZERO)
                            total_period_credit = amounts.get("credit", ZERO)
                        elif "compagnie" in line_text:
                            total_company_debit = amounts.get("debit", ZERO)
                            total_company_credit = amounts.get("credit", ZERO)
    except OSError as error:
        raise FileOperationError(f"Impossible de lire le rapport GL PDF: {path}") from error

    if not entries:
        errors.append(
            ErrorDetail(
                "gl_detail_empty",
                "Le rapport GL PDF ne contient aucune ligne comptable. Utilisez le PDF original généré par EmployeurD, non scanné ni altéré.",
            )
        )
    if current_debit != ZERO or current_credit != ZERO:
        errors.append(
            ErrorDetail(
                "gl_detail_missing_subtotal",
                f"Dernier groupe sans sous-total: débit={current_debit:.2f}, crédit={current_credit:.2f}.",
            )
        )
    if total_company_debit is not None and total_company_debit != debit_total:
        errors.append(
            ErrorDetail(
                "gl_detail_total_mismatch",
                f"Total compagnie débit incohérent: lignes={debit_total:.2f}, total={total_company_debit:.2f}.",
            )
        )
    if total_company_credit is not None and total_company_credit != credit_total:
        errors.append(
            ErrorDetail(
                "gl_detail_total_mismatch",
                f"Total compagnie crédit incohérent: lignes={credit_total:.2f}, total={total_company_credit:.2f}.",
            )
        )
    if total_period_debit is not None and total_period_debit != debit_total:
        errors.append(
            ErrorDetail(
                "gl_detail_total_mismatch",
                f"Total période débit incohérent: lignes={debit_total:.2f}, total={total_period_debit:.2f}.",
            )
        )
    if total_period_credit is not None and total_period_credit != credit_total:
        errors.append(
            ErrorDetail(
                "gl_detail_total_mismatch",
                f"Total période crédit incohérent: lignes={credit_total:.2f}, total={total_period_credit:.2f}.",
            )
        )
    if errors:
        raise ValidationFailed(errors)

    metadata = "\n".join(metadata_text)
    return GLDetailReport(
        source_file=path,
        row_count=len(entries),
        accounting_date=_metadata_date(metadata),
        company=_metadata_value(COMPANY_PATTERN, metadata),
        accounting_period=_metadata_value(PC_PATTERN, metadata),
        payroll_period=_metadata_value(PAYROLL_PERIOD_PATTERN, metadata),
        entries=tuple(entries),
        debit_total=debit_total,
        credit_total=credit_total,
        account_side_totals=dict(account_side_totals),
        subtotal_count=subtotal_count,
        total_company_debit=total_company_debit,
        total_company_credit=total_company_credit,
        total_period_debit=total_period_debit,
        total_period_credit=total_period_credit,
    )


def _group_words_by_line(words: list[dict], *, tolerance: float = 2.0) -> list[list[dict]]:
    lines: list[list[dict]] = []
    current: list[dict] = []
    current_top: float | None = None
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        if current_top is None or abs(top - current_top) <= tolerance:
            current.append(word)
            current_top = top if current_top is None else (current_top * 0.8) + (top * 0.2)
            continue
        lines.append(sorted(current, key=lambda item: float(item["x0"])))
        current = [word]
        current_top = top
    if current:
        lines.append(sorted(current, key=lambda item: float(item["x0"])))
    return lines


def _header_columns(words: list[dict]) -> tuple[float, float] | None:
    debit_x = None
    credit_x = None
    for word in words:
        text = str(word["text"]).lower()
        center = (float(word["x0"]) + float(word["x1"])) / 2
        if text.startswith("débit") or text.startswith("debit"):
            debit_x = center
        elif text.startswith("crédit") or text.startswith("credit"):
            credit_x = center
    if debit_x is None or credit_x is None:
        return None
    return debit_x, credit_x


def _find_account_word(words: list[dict]) -> dict | None:
    for word in words:
        if ACCOUNT_PATTERN.fullmatch(str(word["text"])):
            return word
    return None


def _find_amount_word(words: list[dict], money_area_start: float) -> dict | None:
    amount_words = [
        word
        for word in words
        if float(word["x0"]) > money_area_start - 80 and MONEY_PATTERN.fullmatch(str(word["text"]).replace(" ", ""))
    ]
    return amount_words[-1] if amount_words else None


def _amounts_by_side(words: list[dict], debit_x: float, credit_x: float) -> dict[Side, Decimal]:
    values: dict[Side, Decimal] = {}
    money_area_start = min(debit_x, credit_x)
    for word in words:
        if float(word["x0"]) <= money_area_start - 80:
            continue
        text = str(word["text"]).replace(" ", "")
        if not MONEY_PATTERN.fullmatch(text):
            continue
        side = _word_side(word, debit_x, credit_x)
        value = _decimal_from_text(text)
        if value is not None:
            values[side] = value
    return values


def _word_side(word: dict, debit_x: float, credit_x: float) -> Side:
    center = (float(word["x0"]) + float(word["x1"])) / 2
    return "debit" if abs(center - debit_x) <= abs(center - credit_x) else "credit"


def _parse_decimal(text: str, errors: list[ErrorDetail], line_number: int, field_name: str) -> Decimal | None:
    value = _decimal_from_text(text)
    if value is None:
        errors.append(ErrorDetail("gl_detail_decimal", "Montant GL invalide.", line_number, field_name))
        return None
    if value != value.quantize(CENT):
        errors.append(ErrorDetail("gl_detail_decimal_scale", "Montant GL avec plus de 2 décimales.", line_number, field_name))
        return None
    return value


def _decimal_from_text(text: str) -> Decimal | None:
    cleaned = text.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _description_for_line(words: list[dict], account_word: dict, amount_word: dict) -> str:
    account_x = float(account_word["x1"])
    amount_x = float(amount_word["x0"])
    description_words = [
        str(word["text"])
        for word in words
        if float(word["x0"]) > account_x and float(word["x1"]) < amount_x and str(word["text"]) != "Régulière"
    ]
    return " ".join(description_words).strip()


def _metadata_date(text: str) -> date | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _metadata_value(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None

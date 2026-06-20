from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .errors import ConfigurationError


@dataclass(frozen=True)
class AccountConfig:
    allowed_accounts: frozenset[str]
    conversion_strategy: str = "drop_first_digit"
    source_to_mnd: dict[str, str] | None = None


@dataclass(frozen=True)
class ValidationConfig:
    require_single_batch: bool = True
    require_single_date: bool = True
    require_balanced: bool = True
    debit_credit_tolerance: Decimal = Decimal("0.00")
    reject_zero_amount_lines: bool = True
    reject_unknown_accounts: bool = False
    reject_non_crlf_source: bool = False
    require_crlf_mnd_output: bool = True
    require_mnd_roundtrip: bool = True


@dataclass(frozen=True)
class MndConfig:
    source_label: str = "EmployeurD"
    reference_strategy: str = "employeurd_batch_full"
    batch_strategy: str = "employeurd_batch_last_6_digits"
    extra_field_strategy: str = "blank"
    output_encoding: str = "cp1252"


@dataclass(frozen=True)
class ReportComponentConfig:
    field: str
    type: str | None = None
    codes: tuple[str, ...] = ()
    exclude_codes: tuple[str, ...] = ()
    sign: int = 1


@dataclass(frozen=True)
class ReportTotalConfig:
    label: str
    components: tuple[ReportComponentConfig, ...]


@dataclass(frozen=True)
class SPD640Config:
    enabled: bool = True
    mode: str = "advisory"
    tolerance: Decimal = Decimal("0.00")
    require_matching_batch: bool = True
    require_matching_period: bool = True
    require_matching_date: bool = False
    debit_total: ReportTotalConfig | None = None
    credit_total: ReportTotalConfig | None = None


@dataclass(frozen=True)
class SPD681Config:
    enabled: bool = True
    mode: str = "advisory"
    tolerance: Decimal = Decimal("0.00")
    require_matching_batch: bool = True
    require_matching_period: bool = True
    require_matching_date: bool = False
    warn_on_reported_differences: bool = True


@dataclass(frozen=True)
class ReportsConfig:
    spd640: SPD640Config
    spd681: SPD681Config


@dataclass(frozen=True)
class AppConfig:
    accounts: AccountConfig
    validation: ValidationConfig
    mnd: MndConfig
    reports: ReportsConfig
    updates: dict[str, Any]
    audit_log: dict[str, Any]


def load_app_config(config_dir: Path) -> AppConfig:
    accounts_data = _load_config_file(config_dir / "comptes.yml")
    validation_data = _load_config_file(config_dir / "regles_validation.yml")
    app_data = _load_config_file(config_dir / "app.yml")
    reports_path = config_dir / "rapports.yml"
    reports_data = _load_config_file(reports_path) if reports_path.exists() else {}

    accounts_root = _as_dict(accounts_data.get("accounts"), "accounts")
    validation_root = _as_dict(validation_data.get("validation"), "validation")
    mnd_root = _as_dict(app_data.get("mnd"), "mnd")

    allowed = accounts_root.get("allowed") or []
    if not isinstance(allowed, list):
        raise ConfigurationError("accounts.allowed doit être une liste.")

    allowed_accounts = frozenset(_validate_mnd_account(str(account)) for account in allowed)
    source_to_mnd = accounts_root.get("source_to_mnd") or {}
    if not isinstance(source_to_mnd, dict):
        raise ConfigurationError("accounts.source_to_mnd doit être un objet.")

    mapped_accounts = {str(source): _validate_mnd_account(str(target)) for source, target in source_to_mnd.items()}

    return AppConfig(
        accounts=AccountConfig(
            allowed_accounts=allowed_accounts,
            conversion_strategy=str(accounts_root.get("conversion_strategy", "drop_first_digit")),
            source_to_mnd=mapped_accounts,
        ),
        validation=ValidationConfig(
            require_single_batch=_as_bool(validation_root.get("require_single_batch", True)),
            require_single_date=_as_bool(validation_root.get("require_single_date", True)),
            require_balanced=_as_bool(validation_root.get("require_balanced", True)),
            debit_credit_tolerance=_as_decimal(validation_root.get("debit_credit_tolerance", "0.00")),
            reject_zero_amount_lines=_as_bool(validation_root.get("reject_zero_amount_lines", True)),
            reject_unknown_accounts=_as_bool(validation_root.get("reject_unknown_accounts", False)),
            reject_non_crlf_source=_as_bool(validation_root.get("reject_non_crlf_source", False)),
            require_crlf_mnd_output=_as_bool(validation_root.get("require_crlf_mnd_output", True)),
            require_mnd_roundtrip=_as_bool(validation_root.get("require_mnd_roundtrip", True)),
        ),
        mnd=MndConfig(
            source_label=str(mnd_root.get("source_label", "EmployeurD")),
            reference_strategy=str(mnd_root.get("reference_strategy", "employeurd_batch_full")),
            batch_strategy=str(mnd_root.get("batch_strategy", "employeurd_batch_last_6_digits")),
            extra_field_strategy=str(mnd_root.get("extra_field_strategy", "blank")),
            output_encoding=str(mnd_root.get("output_encoding", "cp1252")),
        ),
        reports=_load_reports_config(reports_data),
        updates=_as_dict(app_data.get("updates", {}), "updates"),
        audit_log=_as_dict(app_data.get("audit_log", {}), "audit_log"),
    )


def _load_reports_config(data: dict[str, Any]) -> ReportsConfig:
    root = _as_dict(data.get("reports", {}), "reports")
    spd640_root = _as_dict(root.get("spd640", {}), "reports.spd640")
    spd681_root = _as_dict(root.get("spd681", {}), "reports.spd681")
    default_total = ReportTotalConfig(
        label="TYPE=G / MONTANTS",
        components=(ReportComponentConfig(type="G", field="MONTANTS"),),
    )
    return ReportsConfig(
        spd640=SPD640Config(
            enabled=_as_bool(spd640_root.get("enabled", True)),
            mode=str(spd640_root.get("mode", "advisory")),
            tolerance=_as_decimal(spd640_root.get("tolerance", "0.00")),
            require_matching_batch=_as_bool(spd640_root.get("require_matching_batch", True)),
            require_matching_period=_as_bool(spd640_root.get("require_matching_period", True)),
            require_matching_date=_as_bool(spd640_root.get("require_matching_date", False)),
            debit_total=_load_report_total(spd640_root.get("debit_total"), default_total, "debit_total"),
            credit_total=_load_report_total(spd640_root.get("credit_total"), default_total, "credit_total"),
        ),
        spd681=SPD681Config(
            enabled=_as_bool(spd681_root.get("enabled", True)),
            mode=str(spd681_root.get("mode", "advisory")),
            tolerance=_as_decimal(spd681_root.get("tolerance", "0.00")),
            require_matching_batch=_as_bool(spd681_root.get("require_matching_batch", True)),
            require_matching_period=_as_bool(spd681_root.get("require_matching_period", True)),
            require_matching_date=_as_bool(spd681_root.get("require_matching_date", False)),
            warn_on_reported_differences=_as_bool(spd681_root.get("warn_on_reported_differences", True)),
        ),
    )


def _load_report_total(value: Any, default: ReportTotalConfig, name: str) -> ReportTotalConfig:
    if value is None:
        return default
    data = _as_dict(value, name)
    components_raw = data.get("components")
    if not isinstance(components_raw, list) or not components_raw:
        raise ConfigurationError(f"{name}.components doit être une liste non vide.")
    return ReportTotalConfig(
        label=str(data.get("label", name)),
        components=tuple(_load_report_component(component, f"{name}.components") for component in components_raw),
    )


def _load_report_component(value: Any, name: str) -> ReportComponentConfig:
    data = _as_dict(value, name)
    field = str(data.get("field", "")).strip()
    if field not in {"MONTANTS", "MNTS/EMPLOYEUR", "MNTS BANQUE"}:
        raise ConfigurationError(f"Champ SPD640 invalide: {field}")
    sign = int(str(data.get("sign", "1")))
    if sign not in {-1, 1}:
        raise ConfigurationError("Le signe d'un composant doit être 1 ou -1.")
    return ReportComponentConfig(
        field=field,
        type=str(data["type"]).strip() if data.get("type") is not None else None,
        codes=tuple(str(code).strip() for code in data.get("codes", []) or ()),
        exclude_codes=tuple(str(code).strip() for code in data.get("exclude_codes", []) or ()),
        sign=sign,
    )


def _load_config_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(f"Impossible de lire la configuration: {path}") from error

    try:
        data = _parse_yaml(text)
    except ValueError as error:
        raise ConfigurationError(f"Configuration invalide: {path}: {error}") from error

    if not isinstance(data, dict):
        raise ConfigurationError(f"La configuration doit être un objet: {path}")
    return data


def _parse_yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        pass

    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(text)

    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        without_comment = raw_line.split("#", 1)[0].rstrip()
        if not without_comment.strip():
            continue
        indent = len(without_comment) - len(without_comment.lstrip(" "))
        lines.append((indent, without_comment.strip()))

    if not lines:
        return {}

    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError("contenu YAML non interprété")
    return value


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index

    first_indent, first_content = lines[index]
    if first_indent != indent:
        raise ValueError("indentation incohérente")

    if first_content.startswith("- "):
        items: list[Any] = []
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent != indent or not content.startswith("- "):
                break
            rest = content[2:].strip()
            if rest:
                index += 1
                if ":" in rest and not rest.startswith(("'", '"')):
                    item = _parse_inline_mapping(rest)
                    if index < len(lines) and lines[index][0] > indent:
                        child, index = _parse_block(lines, index, lines[index][0])
                        if not isinstance(child, dict):
                            raise ValueError("un élément de liste objet doit contenir des clés")
                        item.update(child)
                    items.append(item)
                else:
                    items.append(_parse_scalar(rest))
            else:
                child, index = _parse_block(lines, index + 1, lines[index + 1][0])
                items.append(child)
        return items, index

    data: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent:
            raise ValueError("indentation inattendue")
        if content.startswith("- "):
            break
        key, separator, rest = content.partition(":")
        if not separator:
            raise ValueError(f"ligne invalide: {content}")
        key = key.strip()
        rest = rest.strip()
        if rest:
            data[key] = _parse_scalar(rest)
            index += 1
        else:
            if index + 1 >= len(lines) or lines[index + 1][0] <= current_indent:
                data[key] = None
                index += 1
            else:
                child, index = _parse_block(lines, index + 1, lines[index + 1][0])
                data[key] = child
    return data, index


def _parse_scalar(value: str) -> Any:
    if value == "{}":
        return {}
    if value == "[]":
        return []
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    return value


def _parse_inline_mapping(value: str) -> dict[str, Any]:
    key, separator, rest = value.partition(":")
    if not separator:
        raise ValueError(f"ligne invalide: {value}")
    return {key.strip(): _parse_scalar(rest.strip()) if rest.strip() else None}


def _as_dict(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigurationError(f"{name} doit être un objet.")
    return value


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    raise ConfigurationError(f"Valeur booléenne invalide: {value}")


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise ConfigurationError(f"Nombre décimal invalide: {value}") from error


def _validate_mnd_account(account: str) -> str:
    if len(account) != 10 or not account.isdigit():
        raise ConfigurationError(f"Compte MégaGest invalide: {account}")
    return account

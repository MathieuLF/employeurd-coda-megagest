from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

from .audit_log import write_audit_event
from .config import load_app_config
from .converter import convert_file, inspect_source, validate_file
from .errors import ConfigurationError, ConversionError, FileOperationError, ValidationFailed
from .integrity import check_running_app_integrity
from .parser_mnd import parse_mnd_file
from .parser_employeurd import parse_employeurd_file
from .reports.gl_detail_pdf_parser import parse_gl_detail_pdf
from .reports.spd640_parser import parse_spd640_csv
from .reconciliation import reconcile_gl_detail, reconcile_spd640, reconciliation_failed
from .update_check import check_for_update
from .validator import mnd_totals, validate_source_entries
from .version import __version__


EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_USAGE = 2
EXIT_IO = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="employeurd-megagest",
        description="Convertit un fichier TXT EmployeurD en fichier MND MégaGest.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config-dir", type=Path, default=Path("config"), help="Dossier de configuration avancée.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-source", help="Résume un fichier EmployeurD sans produire de MND.")
    inspect_parser.add_argument("input", type=Path)

    validate_parser = subparsers.add_parser("validate", help="Vérifie le fichier sans écrire de MND.")
    validate_parser.add_argument("input", type=Path)
    validate_parser.add_argument("--period", help="Période forcée AAAAMM.")
    validate_parser.add_argument("--report", type=Path)
    validate_parser.add_argument("--json", type=Path, dest="validation_json")
    validate_parser.add_argument("--overwrite", action="store_true")
    validate_parser.add_argument("--gl-detail", type=Path, help="PDF grand détail de l'écriture GL à comparer.")
    validate_parser.add_argument("--require-gl-detail", action="store_true", help="Bloque si le rapprochement GL PDF échoue.")
    validate_parser.add_argument("--spd640", type=Path, help="Rapport SPD640-P CSV à comparer.")
    validate_parser.add_argument("--require-spd640", action="store_true", help="Bloque si le rapprochement SPD640 échoue.")

    convert_parser = subparsers.add_parser("convert", help="Convertit un fichier EmployeurD TXT vers MND.")
    convert_parser.add_argument("input", type=Path)
    convert_parser.add_argument("output", type=Path)
    convert_parser.add_argument("--period", help="Période forcée AAAAMM.")
    convert_parser.add_argument("--overwrite", action="store_true")
    convert_parser.add_argument("--gl-detail", type=Path, help="PDF grand détail de l'écriture GL à comparer avant la création.")
    convert_parser.add_argument("--require-gl-detail", action="store_true", help="Bloque si le rapprochement GL PDF échoue.")
    convert_parser.add_argument("--spd640", type=Path, help="Rapport SPD640-P CSV à comparer avant la création.")
    convert_parser.add_argument("--require-spd640", action="store_true", help="Bloque si le rapprochement SPD640 échoue.")

    parse_parser = subparsers.add_parser("parse-mnd", help="Parse un fichier MND et affiche ses totaux.")
    parse_parser.add_argument("input", type=Path)

    gl_detail_parser = subparsers.add_parser("parse-gl-detail", help="Lit un PDF grand détail GL et affiche ses totaux.")
    gl_detail_parser.add_argument("input", type=Path)

    spd640_parser = subparsers.add_parser("parse-spd640", help="Lit un rapport SPD640-P CSV et affiche ses totaux.")
    spd640_parser.add_argument("input", type=Path)

    reconcile_gl_parser = subparsers.add_parser("reconcile-gl-detail", help="Compare un TXT EmployeurD avec un PDF grand détail GL.")
    reconcile_gl_parser.add_argument("source", type=Path)
    reconcile_gl_parser.add_argument("gl_detail", type=Path)

    reconcile_parser = subparsers.add_parser("reconcile-spd640", help="Compare un TXT EmployeurD avec un rapport SPD640-P CSV.")
    reconcile_parser.add_argument("source", type=Path)
    reconcile_parser.add_argument("spd640", type=Path)

    subparsers.add_parser("check-update", help="Vérifie si une nouvelle version est disponible.")

    subparsers.add_parser("check-integrity", help="Vérifie l'intégrité de la version ouverte.")

    subparsers.add_parser("self-test", help="Lance les tests unitaires locaux.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "self-test":
            return _run_self_tests()

        config = load_app_config(args.config_dir)

        if args.command == "inspect-source":
            result = inspect_source(args.input, config)
            _print_result(result.row_count, result.total_debit, result.total_credit, result.period, result.batch)
            _audit(config, "inspect_source", "success", {"row_count": result.row_count, "period": result.period})
            return EXIT_OK

        if args.command == "validate":
            reconciliations = _collect_control_reconciliations(args, args.input, config)
            result = validate_file(
                args.input,
                config,
                period=args.period,
                report_path=args.report,
                validation_json_path=args.validation_json,
                overwrite=args.overwrite,
                reconciliations=reconciliations,
            )
            _print_result(result.row_count, result.total_debit, result.total_credit, result.period, result.batch)
            if result.report_path:
                print(f"rapport={result.report_path}")
            if result.validation_json_path:
                print(f"json={result.validation_json_path}")
            _audit(config, "validate", "success", {"row_count": result.row_count, "reconciliations": len(reconciliations)})
            return EXIT_OK

        if args.command == "convert":
            reconciliations = _collect_control_reconciliations(args, args.input, config)
            result = convert_file(args.input, args.output, config, period=args.period, overwrite=args.overwrite, reconciliations=reconciliations)
            _print_result(result.row_count, result.total_debit, result.total_credit, result.period, result.batch)
            print(f"sortie={result.output_path}")
            print(f"rapport={result.report_path}")
            print(f"json={result.validation_json_path}")
            _audit(config, "convert", "success", {"row_count": result.row_count, "period": result.period, "reconciliations": len(reconciliations)})
            return EXIT_OK

        if args.command == "parse-mnd":
            entries = parse_mnd_file(args.input, require_crlf=config.validation.require_crlf_mnd_output, encoding=config.mnd.output_encoding)
            debit, credit = mnd_totals(entries)
            _print_result(len(entries), debit, credit, entries[0].period if entries else None, entries[0].batch if entries else None)
            return EXIT_OK

        if args.command == "parse-gl-detail":
            report = parse_gl_detail_pdf(args.input)
            _print_gl_detail_report(report)
            return EXIT_OK

        if args.command == "parse-spd640":
            report = parse_spd640_csv(args.input)
            _print_spd640_report(report)
            return EXIT_OK

        if args.command == "reconcile-gl-detail":
            result = _handle_gl_detail_reconciliation(args.source, args.gl_detail, config, require=True)
            if reconciliation_failed(result):
                raise ValidationFailed(
                    f"Rapprochement GL PDF en écart: débit={result.debit_difference:.2f}, crédit={result.credit_difference:.2f}."
                )
            _audit(config, "reconcile_gl_detail", "success", {})
            return EXIT_OK

        if args.command == "reconcile-spd640":
            result = _handle_spd640_reconciliation(args.source, args.spd640, config, require=True)
            if reconciliation_failed(result):
                raise ValidationFailed(
                    f"Rapprochement SPD640 en écart: débit={result.debit_difference:.2f}, crédit={result.credit_difference:.2f}."
                )
            _audit(config, "reconcile_spd640", "success", {})
            return EXIT_OK

        if args.command == "check-update":
            result = check_for_update(str(config.updates.get("url", "")))
            print(f"ok={str(result.ok).lower()}")
            print(f"update_available={str(result.update_available).lower()}")
            print(f"current_version={result.current_version}")
            print(f"latest_version={result.latest_version or 'n/d'}")
            print(f"sha256={result.sha256 or 'n/d'}")
            print(f"message={result.message}")
            return EXIT_OK

        if args.command == "check-integrity":
            result = check_running_app_integrity(str(config.updates.get("url", "")))
            print(f"status={result.status}")
            print(f"verified={str(result.verified).lower()}")
            print(f"current_version={result.current_version}")
            print(f"executable={result.executable_path}")
            print(f"local_sha256={result.local_sha256 or 'n/d'}")
            print(f"expected_sha256={result.expected_sha256 or 'n/d'}")
            print(f"signature={result.signature_status}")
            print(f"message={result.message}")
            if result.status == "mismatch":
                return EXIT_VALIDATION
            if result.status == "unavailable":
                return EXIT_USAGE
            return EXIT_OK

    except ValidationFailed as error:
        if "config" in locals():
            _audit(config, "validation", "failed", {"errors": [detail.code for detail in error.errors]})
        print("Validation bloquante:", file=sys.stderr)
        for detail in error.errors:
            print(f"- {detail.format()}", file=sys.stderr)
        return EXIT_VALIDATION
    except FileOperationError as error:
        print(f"Erreur fichier: {error}", file=sys.stderr)
        return EXIT_IO
    except ConfigurationError as error:
        print(f"Erreur configuration: {error}", file=sys.stderr)
        return EXIT_USAGE
    except ConversionError as error:
        print(f"Erreur: {error}", file=sys.stderr)
        return EXIT_USAGE

    parser.error("Commande inconnue.")
    return EXIT_USAGE


def _audit(config, event: str, status: str, details: dict) -> None:
    audit_config = getattr(config, "audit_log", {})
    if not audit_config.get("enabled", False):
        return
    log_dir = Path(audit_config["directory"]) if audit_config.get("directory") else None
    try:
        write_audit_event(event, status=status, details=details, log_dir=log_dir)
    except OSError:
        pass


def _print_result(row_count: int, debit, credit, period: str | None, batch: str | None) -> None:
    print(f"lignes={row_count}")
    print(f"debit={debit:.2f}")
    print(f"credit={credit:.2f}")
    print(f"periode={period or 'n/d'}")
    print(f"lot={batch or 'n/d'}")


def _run_self_tests() -> int:
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return EXIT_OK if result.wasSuccessful() else EXIT_VALIDATION


def _handle_spd640_reconciliation(source_path: Path, report_path: Path, config, *, require: bool):
    entries = parse_employeurd_file(source_path, reject_non_crlf=config.validation.reject_non_crlf_source)
    validate_source_entries(entries, config.validation)
    result = reconcile_spd640(entries, report_path, config, required=require or None)
    _print_spd640_reconciliation(result)
    return result


def _handle_gl_detail_reconciliation(source_path: Path, report_path: Path, config, *, require: bool):
    entries = parse_employeurd_file(source_path, reject_non_crlf=config.validation.reject_non_crlf_source)
    validate_source_entries(entries, config.validation)
    result = reconcile_gl_detail(entries, report_path, config, required=require or None)
    _print_gl_detail_reconciliation(result)
    return result


def _collect_control_reconciliations(args, source_path: Path, config) -> list:
    reconciliations = []
    gl_detail_path = getattr(args, "gl_detail", None)
    if gl_detail_path:
        require = bool(getattr(args, "require_gl_detail", False))
        reconciliations.append(_handle_gl_detail_reconciliation(source_path, gl_detail_path, config, require=require))
    spd640_path = getattr(args, "spd640", None)
    if spd640_path:
        require = bool(getattr(args, "require_spd640", False))
        reconciliations.append(_handle_spd640_reconciliation(source_path, spd640_path, config, require=require))
    return reconciliations


def _print_gl_detail_report(report) -> None:
    print(f"lignes={report.row_count}")
    print(f"compagnie={report.company or 'n/d'}")
    print(f"date_ecriture={report.accounting_date.isoformat() if report.accounting_date else 'n/d'}")
    print(f"periode={report.period or 'n/d'}")
    print(f"pc={report.accounting_period or 'n/d'}")
    print(f"periode_paie={report.payroll_period or 'n/d'}")
    print(f"sous_totaux={report.subtotal_count}")
    print(f"debit={report.debit_total:.2f}")
    print(f"credit={report.credit_total:.2f}")


def _print_spd640_report(report) -> None:
    payroll_totals = report.to_payroll_totals()
    print(f"lignes={report.row_count}")
    print(f"lot={report.batch or 'n/d'}")
    print(f"periode={report.period or 'n/d'}")
    print(f"dates_comptables={','.join(date.isoformat() for date in report.accounting_dates) or 'n/d'}")
    print(f"type_g_montants={payroll_totals.other_totals['type_g_montants']:.2f}")
    print(f"type_d_montants={payroll_totals.other_totals['type_d_montants']:.2f}")
    print(f"mnts_employeur={payroll_totals.other_totals['mnts_employeur']:.2f}")
    print(f"mnts_banque={payroll_totals.other_totals['mnts_banque']:.2f}")


def _print_spd640_reconciliation(result) -> None:
    status = "OK" if result.status == "success" else "ECART" if result.status == "failed" else "IGNORE"
    print(f"spd640={status}")
    print(f"spd640_debit_label={result.debit_label}")
    print(f"spd640_credit_label={result.credit_label}")
    print(f"source_debit={result.source_debit:.2f}")
    print(f"source_credit={result.source_credit:.2f}")
    print(f"spd640_debit={result.report_debit:.2f}")
    print(f"spd640_credit={result.report_credit:.2f}")
    print(f"debit_difference={result.debit_difference:.2f}")
    print(f"credit_difference={result.credit_difference:.2f}")


def _print_gl_detail_reconciliation(result) -> None:
    status = "OK" if result.status == "success" else "ECART" if result.status == "failed" else "IGNORE"
    print(f"gl_detail={status}")
    print(f"source_debit={result.source_debit:.2f}")
    print(f"source_credit={result.source_credit:.2f}")
    print(f"gl_detail_debit={result.report_debit:.2f}")
    print(f"gl_detail_credit={result.report_credit:.2f}")
    print(f"debit_difference={result.debit_difference:.2f}")
    print(f"credit_difference={result.credit_difference:.2f}")
    print(f"account_mismatch_count={result.details.get('account_mismatch_count', '0')}")

from __future__ import annotations

import sys
import tempfile
import unittest
import json
import os
import subprocess
import urllib.error
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from employeurd_megagest.config import load_app_config
from employeurd_megagest.converter import convert_file
from employeurd_megagest.audit_log import write_audit_event
from employeurd_megagest.errors import ValidationFailed
from employeurd_megagest.app_gui import _generated_outputs_message, _usable_saved_output_dir
from employeurd_megagest.gui_controller import GuiController, GuiOperationResult
from employeurd_megagest.gui_state import GuiViewState, build_file_preview, build_metrics, build_output_preview, default_output_root
from employeurd_megagest.integrity import IntegrityCheckResult, app_package_sha256, check_running_app_integrity
from employeurd_megagest.output_plan import build_output_plan
from employeurd_megagest.parser_employeurd import parse_employeurd_file, parse_employeurd_line
from employeurd_megagest.parser_mnd import parse_mnd_file, parse_mnd_text
from employeurd_megagest.preferences import (
    AppPreferences,
    load_preferences,
    remember_output_dir,
    remember_update_check_on_startup,
    save_preferences,
)
from employeurd_megagest.reconciliation import reconcile_control_report, reconcile_spd640, reconcile_spd681, reconciliation_failed
from employeurd_megagest.reports.spd640_parser import parse_spd640_csv, reconcile_spd640_with_source_totals
from employeurd_megagest.reports.spd681_parser import parse_spd681_xml
from employeurd_megagest.resource_paths import package_asset_path
from employeurd_megagest.update_check import DEFAULT_UPDATE_URL, check_for_update
from employeurd_megagest.validator import convert_account, mnd_totals, source_totals
from employeurd_megagest.writer_mnd import MND_LINE_LENGTH
from scripts import append_release_verification, generate_release_manifest, submit_virustotal
from scripts.submit_virustotal import collect_detections


class EmployeurDMegaGestTest(unittest.TestCase):
    def config(self):
        root = Path(__file__).resolve().parents[1]
        return load_app_config(root / "config")

    def test_parse_employeurd_fixed_width_source(self) -> None:
        root = Path(__file__).resolve().parents[1]
        entries = parse_employeurd_file(root / "samples" / "employeurd-balanced.txt")

        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[0].batch, "00001234")
        self.assertEqual(entries[0].account, "50213000140")
        self.assertEqual(entries[0].amount, Decimal("1000.00"))
        self.assertEqual(entries[0].entry_date.strftime("%Y%m%d"), "20260618")

    def test_product_icon_assets_are_present(self) -> None:
        root = Path(__file__).resolve().parents[1]

        self.assertTrue(package_asset_path("app-icon.png").exists())
        self.assertTrue((root / "packaging" / "windows" / "EmployeurD-MegaGest.ico").exists())
        self.assertTrue((root / "docs" / "assets" / "product-icon.png").exists())
        self.assertIn("--icon", (root / "scripts" / "build_exe.ps1").read_text(encoding="utf-8"))

    def test_source_totals_balance_with_decimal(self) -> None:
        root = Path(__file__).resolve().parents[1]
        entries = parse_employeurd_file(root / "samples" / "employeurd-balanced.txt")
        debit, credit = source_totals(entries)

        self.assertEqual(debit, Decimal("1250.50"))
        self.assertEqual(credit, Decimal("1250.50"))

    def test_reject_invalid_source_length(self) -> None:
        with self.assertRaises(ValidationFailed):
            parse_employeurd_line("trop court", 1)

    def test_reject_invalid_source_amount_precision(self) -> None:
        line = "00001234" + " " + "50213000140" + "1000.001".rjust(49) + "20260618"
        with self.assertRaises(ValidationFailed):
            parse_employeurd_line(line, 1)

    def test_reject_invalid_source_date(self) -> None:
        line = "00001234" + " " + "50213000140" + "1000.00".rjust(49) + "20260231"
        with self.assertRaises(ValidationFailed):
            parse_employeurd_line(line, 1)

    def test_convert_account_by_dropping_first_digit(self) -> None:
        config = self.config()

        self.assertEqual(convert_account("50213000140", config.accounts), "0213000140")
        self.assertEqual(convert_account("55411200000", config.accounts), "5411200000")

    def test_convert_balanced_source_to_mnd_with_reports(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            result = convert_file(root / "samples" / "employeurd-balanced.txt", output, config)

            self.assertEqual(result.row_count, 4)
            self.assertEqual(result.total_debit, result.total_credit)
            output_bytes = output.read_bytes()
            self.assertTrue(output_bytes.endswith(b"\r\n"))
            self.assertNotIn(b"\r\r\n", output_bytes)
            self.assertTrue(output.with_suffix(".rapport.md").exists())
            self.assertTrue(output.with_suffix(".validation.json").exists())

            logical_lines = output.read_text(encoding="cp1252").splitlines()
            self.assertTrue(all(len(line) == MND_LINE_LENGTH for line in logical_lines))
            payload = json.loads(output.with_suffix(".validation.json").read_text(encoding="utf-8"))

            self.assertEqual(result.reconciliations[0].report_type, "MND")
            self.assertEqual(result.reconciliations[0].status, "success")
            self.assertEqual(payload["reconciliations"][0]["report_type"], "MND")
            self.assertEqual(payload["reconciliations"][0]["debit_difference"], "0.00")

    def test_convert_can_skip_optional_report_and_json(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            result = convert_file(
                root / "samples" / "employeurd-balanced.txt",
                output,
                config,
                write_report=False,
                write_validation_json=False,
            )

            self.assertTrue(output.exists())
            self.assertIsNone(result.report_path)
            self.assertIsNone(result.validation_json_path)
            self.assertFalse(output.with_suffix(".rapport.md").exists())
            self.assertFalse(output.with_suffix(".validation.json").exists())

    def test_gui_generation_message_matches_selected_outputs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        source = root / "samples" / "employeurd-balanced.txt"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            mnd_only = convert_file(source, output, config, write_report=False, write_validation_json=False)

            output_with_report = Path(directory) / "output-report.mnd"
            report_only = convert_file(source, output_with_report, config, write_validation_json=False)

            output_with_all = Path(directory) / "output-all.mnd"
            all_outputs = convert_file(source, output_with_all, config)

        self.assertEqual(
            _generated_outputs_message(GuiOperationResult(ok=True, message="", conversion=mnd_only)),
            "Le fichier MND a été généré.",
        )
        self.assertEqual(
            _generated_outputs_message(GuiOperationResult(ok=True, message="", conversion=report_only)),
            "Le fichier MND et le rapport Markdown ont été générés.",
        )
        self.assertEqual(
            _generated_outputs_message(GuiOperationResult(ok=True, message="", conversion=all_outputs)),
            "Le fichier MND, le rapport Markdown et le JSON de validation ont été générés.",
        )

    def test_parse_generated_mnd_and_roundtrip_totals(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            convert_file(root / "samples" / "employeurd-balanced.txt", output, config)

            entries = parse_mnd_file(output)
            debit, credit = mnd_totals(entries)

            self.assertEqual(len(entries), 4)
            self.assertEqual(debit, Decimal("1250.50"))
            self.assertEqual(credit, Decimal("1250.50"))
            self.assertEqual(entries[0].period, "202606")
            self.assertEqual(entries[0].reference, "00001234")
            self.assertEqual(entries[0].batch, "001234")

    def test_reject_unbalanced_entries(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            with self.assertRaises(ValidationFailed):
                convert_file(root / "samples" / "employeurd-unbalanced.txt", output, config)

            self.assertFalse(output.exists())
            self.assertTrue(output.with_suffix(".rapport.md").exists())
            self.assertTrue(output.with_suffix(".validation.json").exists())

    def test_accepts_other_gl_accounts_by_default(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            result = convert_file(root / "samples" / "employeurd-unknown-account.txt", output, config)
            self.assertTrue(output.exists())

        self.assertEqual(result.status, "success")

    def test_reject_output_overwrite_without_flag(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            output.write_text("existe", encoding="utf-8")

            with self.assertRaises(ValidationFailed):
                convert_file(root / "samples" / "employeurd-balanced.txt", output, config)

    def test_reject_corrupt_mnd_length(self) -> None:
        with self.assertRaises(ValidationFailed):
            parse_mnd_text("P" + "\r\n")

    def test_parse_spd640_synthetic_report(self) -> None:
        root = Path(__file__).resolve().parents[1]
        report = parse_spd640_csv(root / "samples" / "OPD_RP_00001234_SPD640-P_SYNTHETIQUE.CSV")
        totals = report.to_payroll_totals()

        self.assertEqual(report.row_count, 3)
        self.assertEqual(report.batch, "00001234")
        self.assertEqual(report.period, "202606")
        self.assertEqual(totals.other_totals["type_g_montants"], Decimal("1250.50"))
        self.assertEqual(totals.other_totals["type_d_montants"], Decimal("100.00"))

    def test_parse_spd681_synthetic_report(self) -> None:
        root = Path(__file__).resolve().parents[1]
        report = parse_spd681_xml(root / "samples" / "OPD_RP_00005678_SPD681_SYNTHETIQUE.XML")
        totals = report.to_payroll_totals()

        self.assertEqual(report.row_count, 2)
        self.assertEqual(report.batch, "00005678")
        self.assertEqual(report.period, "202606")
        self.assertEqual(report.difference_threshold, Decimal("1.00"))
        self.assertEqual(report.max_absolute_difference, Decimal("0.00"))
        self.assertEqual(totals.other_totals["rrq_paid"], Decimal("375.02"))
        self.assertEqual(totals.other_totals["ae_paid"], Decimal("81.25"))
        self.assertEqual(totals.other_totals["rqap_paid"], Decimal("26.88"))

    def test_reconcile_spd681_control_report(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        entries = parse_employeurd_file(root / "samples" / "employeurd-spd681-balanced.txt")
        report = root / "samples" / "OPD_RP_00005678_SPD681_SYNTHETIQUE.XML"

        result = reconcile_spd681(entries, report, config, required=False)

        self.assertEqual(result.report_type, "SPD681")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.source_debit, Decimal("6250.25"))
        self.assertEqual(result.details["rrq_paid"], "375.02")
        self.assertTrue(any(message.code == "spd681_scope" for message in result.messages))

    def test_required_spd681_reported_difference_blocks(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        entries = parse_employeurd_file(root / "samples" / "employeurd-spd681-balanced.txt")
        report = root / "samples" / "OPD_RP_00005678_SPD681_ECART_SYNTHETIQUE.XML"

        result = reconcile_spd681(entries, report, config, required=True)

        self.assertTrue(reconciliation_failed(result))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.details["max_absolute_difference"], "2.00")

    def test_control_report_auto_detects_spd681_xml(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        entries = parse_employeurd_file(root / "samples" / "employeurd-spd681-balanced.txt")
        report = root / "samples" / "OPD_RP_00005678_SPD681_SYNTHETIQUE.XML"

        result = reconcile_control_report(entries, report, config, required=False)

        self.assertEqual(result.report_type, "SPD681")
        self.assertEqual(result.status, "success")

    def test_conversion_artifacts_include_spd681_details(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        source = root / "samples" / "employeurd-spd681-balanced.txt"
        report = root / "samples" / "OPD_RP_00005678_SPD681_SYNTHETIQUE.XML"
        entries = parse_employeurd_file(source)
        reconciliation = reconcile_control_report(entries, report, config, required=False)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            result = convert_file(source, output, config, reconciliations=[reconciliation])
            payload = json.loads(output.with_suffix(".validation.json").read_text(encoding="utf-8"))
            markdown = output.with_suffix(".rapport.md").read_text(encoding="utf-8")

        self.assertEqual(result.reconciliations[0].report_type, "MND")
        self.assertEqual(result.reconciliations[0].status, "success")
        spd681_payload = next(item for item in payload["reconciliations"] if item["report_type"] == "SPD681")
        self.assertEqual(spd681_payload["details"]["rrq_paid"], "375.02")
        self.assertIn("SPD681", markdown)
        self.assertIn("Détails de contrôle", markdown)

    def test_reconcile_spd640_with_source_totals(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        source_entries = parse_employeurd_file(root / "samples" / "employeurd-balanced.txt")
        source_debit, source_credit = source_totals(source_entries)
        report = parse_spd640_csv(root / "samples" / "OPD_RP_00001234_SPD640-P_SYNTHETIQUE.CSV")

        result = reconcile_spd640_with_source_totals(
            report,
            source_debit=source_debit,
            source_credit=source_credit,
            config=config.reports.spd640,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.report_debit, Decimal("1250.50"))
        self.assertEqual(result.report_credit, Decimal("1250.50"))

    def test_reconcile_spd640_detects_difference(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        report = parse_spd640_csv(root / "samples" / "OPD_RP_00001234_SPD640-P_SYNTHETIQUE.CSV")

        result = reconcile_spd640_with_source_totals(
            report,
            source_debit=Decimal("10.00"),
            source_credit=Decimal("10.00"),
            config=config.reports.spd640,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.debit_difference, Decimal("-1240.50"))

    def test_spd640_formula_includes_employer_and_vacation_bank_only(self) -> None:
        config = self.config()
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "OPD_RP_00009999_SPD640-P_SYNTHETIQUE.CSV"
            report_path.write_text(
                "COMPAGNIE;DATE COMPTABLE;DIV. OU TRA#1;SERV. OU TRA#2;DEPT. OU TRA#3;S-DEPT. OU TRA#4;TRA#5;TRA#6;RELEVES;DATE;MATRICULE;NOM, PRENOM;TYPE;CODE;DESCRIPTION CODE;QUANTITES;TAUX;MONTANTS;MNTS/EMPLOYEUR;QUANTITES BANQUE;MNTS BANQUE\n"
                "1;2026-06-18;;130;131;;;;;;1;TEST, ALPHA;G;1;HRES REGULIERES;0.00;0.00;1000.00;0.00;0.00;0.00\n"
                "1;2026-06-18;;130;131;;;;;;1;TEST, ALPHA;D;6;FSS;0.00;0.00;0.00;200.00;0.00;0.00\n"
                "1;2026-06-18;;130;131;;;;;;1;TEST, ALPHA;G;305;BQ. VACANCES $;0.00;0.00;0.00;0.00;0.00;50.50\n"
                "1;2026-06-18;;130;131;;;;;;1;TEST, ALPHA;G;113;BQ HRES PAYEES;0.00;0.00;0.00;0.00;0.00;999.99\n",
                encoding="utf-8",
            )
            report = parse_spd640_csv(report_path)

        result = reconcile_spd640_with_source_totals(
            report,
            source_debit=Decimal("1250.50"),
            source_credit=Decimal("1250.50"),
            config=config.reports.spd640,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.report_debit, Decimal("1250.50"))

    def test_conversion_artifacts_include_spd640_reconciliation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        source = root / "samples" / "employeurd-balanced.txt"
        spd = root / "samples" / "OPD_RP_00001234_SPD640-P_SYNTHETIQUE.CSV"
        entries = parse_employeurd_file(source)
        reconciliation = reconcile_spd640(entries, spd, config, required=True)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            convert_file(source, output, config, reconciliations=[reconciliation])
            payload = json.loads(output.with_suffix(".validation.json").read_text(encoding="utf-8"))
            markdown = output.with_suffix(".rapport.md").read_text(encoding="utf-8")

        spd640_payload = next(item for item in payload["reconciliations"] if item["report_type"] == "SPD640")
        self.assertEqual(spd640_payload["status"], "success")
        self.assertIn("## Rapprochements", markdown)
        self.assertIn("SPD640", markdown)

    def test_required_spd640_batch_mismatch_blocks_and_writes_failure_artifacts(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = self.config()
        source = root / "samples" / "employeurd-balanced.txt"
        source_entries = parse_employeurd_file(source)
        source_spd = root / "samples" / "OPD_RP_00001234_SPD640-P_SYNTHETIQUE.CSV"
        with tempfile.TemporaryDirectory() as directory:
            bad_spd = Path(directory) / "OPD_RP_99999999_SPD640-P_SYNTHETIQUE.CSV"
            bad_spd.write_text(source_spd.read_text(encoding="utf-8"), encoding="utf-8")
            reconciliation = reconcile_spd640(source_entries, bad_spd, config, required=True)
            output = Path(directory) / "output.mnd"
            with self.assertRaises(ValidationFailed):
                convert_file(source, output, config, reconciliations=[reconciliation])
            payload = json.loads(output.with_suffix(".validation.json").read_text(encoding="utf-8"))

        self.assertTrue(reconciliation_failed(reconciliation))
        self.assertFalse(output.exists())
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["reconciliations"][0]["status"], "failed")

    def test_output_plan_uses_unique_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 6, 18, 12, 30, 0)
            first = build_output_plan(Path("GL 2026.txt"), root, now=now)
            first.directory.mkdir(parents=True)
            second = build_output_plan(Path("GL 2026.txt"), root, now=now)

        self.assertEqual(first.directory.name, "20260618-123000")
        self.assertEqual(second.directory.name, "20260618-123000-2")
        self.assertEqual(first.mnd_path.name, "GL_2026.mnd")

    def test_output_plan_uses_entry_date_and_batch_for_mnd_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = build_output_plan(
                Path("source.txt"),
                Path(directory),
                now=datetime(2026, 6, 18, 12, 30, 0),
                entry_date=date(2026, 6, 15),
                batch="00001234",
            )

        self.assertEqual(plan.mnd_path.name, "EmployeurD_20260615_lot_00001234.mnd")

    def test_output_plan_can_skip_optional_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = build_output_plan(
                Path("GL20260618.txt"),
                Path(directory),
                now=datetime(2026, 6, 18, 12, 30, 0),
                include_report=False,
                include_validation_json=False,
            )

        self.assertEqual(plan.directory.name, "20260618-123000")
        self.assertEqual(plan.mnd_path.name, "GL20260618.mnd")
        self.assertIsNone(plan.report_path)
        self.assertIsNone(plan.validation_json_path)

    def test_audit_log_sanitizes_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = write_audit_event(
                "convert",
                status="success",
                details={"source_path": Path("C:/secret/payroll.txt"), "row_count": 4},
                log_dir=Path(directory),
            )
            payload = log_path.read_text(encoding="utf-8")

        self.assertIn('"row_count": 4', payload)
        self.assertNotIn("payroll.txt", payload)
        self.assertNotIn("C:/secret", payload)

    def test_update_check_uses_manifest_without_payroll_data(self) -> None:
        with patch("employeurd_megagest.update_check._fetch_json") as fetch:
            fetch.return_value = {
                "latest_version": "0.1.1",
                "download_url": "https://example.invalid/app.exe",
                "sha256": "abc",
                "published_at": "2026-06-18T12:00:00Z",
                "release_notes": "Notes synthétiques",
            }
            result = check_for_update("https://example.invalid/latest.json", current_version="0.1.0")

        self.assertTrue(result.ok)
        self.assertTrue(result.update_available)
        self.assertEqual(result.latest_version, "0.1.1")
        self.assertEqual(result.published_at, "2026-06-18T12:00:00Z")
        self.assertEqual(result.release_notes, "Notes synthétiques")

    def test_update_check_reads_github_release_assets(self) -> None:
        expected_hash = "a" * 64
        with (
            patch("employeurd_megagest.update_check._fetch_json") as fetch_json,
            patch("employeurd_megagest.update_check._fetch_text") as fetch_text,
        ):
            fetch_json.return_value = {
                "tag_name": "v0.1.1",
                "html_url": "https://example.invalid/releases/v0.1.1",
                "assets": [
                    {
                        "name": "EmployeurD-MegaGest-v0.1.1-portable.zip",
                        "browser_download_url": "https://example.invalid/app-portable.zip",
                    },
                    {
                        "name": "EmployeurD-MegaGest-v0.1.1-portable.zip.sha256",
                        "browser_download_url": "https://example.invalid/app.zip.sha256",
                    },
                ],
            }
            fetch_text.return_value = f"{expected_hash.upper()}  EmployeurD-MegaGest-v0.1.1-portable.zip"

            result = check_for_update(DEFAULT_UPDATE_URL, current_version="0.1.0")

        self.assertTrue(result.ok)
        self.assertEqual(result.download_url, "https://example.invalid/app-portable.zip")
        self.assertEqual(result.sha256, expected_hash)

    def test_update_check_uses_default_url_when_config_is_blank_or_placeholder(self) -> None:
        with patch("employeurd_megagest.update_check._fetch_json") as fetch:
            fetch.return_value = {"tag_name": "v0.1.0", "html_url": "https://example.invalid/release"}

            blank = check_for_update("", current_version="0.1.0")
            placeholder = check_for_update(
                "https://api.github.com/repos/<owner>/<repo>/releases/latest",
                current_version="0.1.0",
            )

        self.assertTrue(blank.ok)
        self.assertTrue(placeholder.ok)
        self.assertEqual(fetch.call_args_list[0].args[0], DEFAULT_UPDATE_URL)
        self.assertEqual(fetch.call_args_list[1].args[0], DEFAULT_UPDATE_URL)

    def test_update_check_reports_missing_public_release_cleanly(self) -> None:
        error = urllib.error.HTTPError(DEFAULT_UPDATE_URL, 404, "Not Found", {}, None)
        with patch("employeurd_megagest.update_check._fetch_json", side_effect=error):
            result = check_for_update(DEFAULT_UPDATE_URL, current_version="0.1.0")

        self.assertFalse(result.ok)
        self.assertIn("Aucune mise en ligne officielle", result.message)

    def test_integrity_check_compares_running_package_to_release_hash(self) -> None:
        expected_hash = "b" * 64
        local = IntegrityCheckResult(
            status="local",
            current_version="0.1.0",
            executable_path=Path("EmployeurD-MegaGest.exe"),
            local_sha256=expected_hash,
            expected_sha256=None,
            signature_status="NotSigned",
            release_url=None,
            message="local",
        )
        with (
            patch("employeurd_megagest.integrity.local_integrity_details", return_value=local),
            patch("employeurd_megagest.integrity._fetch_json") as fetch_json,
            patch("employeurd_megagest.integrity._fetch_text") as fetch_text,
        ):
            fetch_json.return_value = {
                "tag_name": "v0.1.0",
                "assets": [
                    {
                        "name": "EmployeurD-MegaGest-v0.1.0.package.sha256",
                        "browser_download_url": "https://example.invalid/app.package.sha256",
                    }
                ],
            }
            fetch_text.return_value = f"{expected_hash.upper()}  EmployeurD-MegaGest-v0.1.0-package"

            result = check_running_app_integrity(DEFAULT_UPDATE_URL, current_version="0.1.0", frozen=True)

        self.assertTrue(result.verified)
        self.assertEqual(result.expected_sha256, expected_hash)
        self.assertTrue(result.release_url.endswith("/releases/tags/v0.1.0"))

    def test_package_integrity_hash_changes_when_package_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            (root / "lib" / "library.zip").write_text("version 1", encoding="utf-8")
            (root / "EmployeurD-MegaGest.exe").write_text("launcher", encoding="utf-8")

            first = app_package_sha256(root)
            (root / "lib" / "library.zip").write_text("version 2", encoding="utf-8")
            second = app_package_sha256(root)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)

    def test_preferences_default_blank_and_persist_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"

            self.assertEqual(load_preferences(path).output_dir, "")
            save_preferences(AppPreferences(output_dir=" C:/Sorties ", update_check_on_startup=True), path=path)
            self.assertEqual(load_preferences(path).output_dir, "C:/Sorties")
            self.assertTrue(load_preferences(path).update_check_on_startup)
            remember_output_dir("D:/Paie/MND", path=path)
            self.assertEqual(load_preferences(path).output_dir, "D:/Paie/MND")
            self.assertTrue(load_preferences(path).update_check_on_startup)
            remember_update_check_on_startup(False, path=path)
            self.assertFalse(load_preferences(path).update_check_on_startup)

    def test_gui_state_previews_files_and_output(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = root / "samples" / "employeurd-balanced.txt"
        with tempfile.TemporaryDirectory() as directory:
            source_preview = build_file_preview(str(source), label="EmployeurD", suffixes=(".txt",), optional=False)
            output_preview = build_output_preview(str(source), directory)
            default_preview = build_output_preview(
                str(source),
                "",
                include_report=False,
                include_validation_json=False,
            )

        self.assertTrue(source_preview.ok)
        self.assertIn("employeurd-balanced.txt", source_preview.detail)
        self.assertTrue(output_preview.ok)
        self.assertIn(".mnd", "\n".join(output_preview.files))
        self.assertTrue(default_preview.ok)
        self.assertEqual(default_preview.directory.parent, default_output_root())
        self.assertEqual(default_preview.files, ("EmployeurD_20260618_lot_00001234.mnd",))

    def test_gui_ignores_temporary_saved_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(_usable_saved_output_dir(directory), "")
        self.assertEqual(_usable_saved_output_dir("C:/Sorties"), "C:/Sorties")

    def test_gui_state_rejects_output_path_that_is_file(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = root / "samples" / "employeurd-balanced.txt"
        with tempfile.TemporaryDirectory() as directory:
            output_file = Path(directory) / "sortie.txt"
            output_file.write_text("pas un dossier", encoding="utf-8")
            output_preview = build_output_preview(str(source), str(output_file))

        self.assertFalse(output_preview.ok)
        self.assertIn("pas un dossier", output_preview.detail)

    def test_gui_controller_requires_spd640_in_strict_mode(self) -> None:
        root = Path(__file__).resolve().parents[1]
        controller = GuiController(config_dir=root / "config")

        with self.assertRaises(ValidationFailed):
            controller.validate(
                source_path=root / "samples" / "employeurd-balanced.txt",
                spd640_path=None,
                require_spd640=True,
            )

    def test_gui_view_state_blocks_generation_until_validation_success(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = root / "samples" / "employeurd-balanced.txt"
        with tempfile.TemporaryDirectory() as directory:
            state = GuiViewState(input_file_path=source, spd640_path=None, output_dir=Path(directory))
            self.assertTrue(state.can_validate)
            self.assertFalse(state.can_generate)

            result = convert_file(source, Path(directory) / "preview.mnd", self.config())
            state = GuiViewState(input_file_path=source, spd640_path=None, output_dir=Path(directory), validation_result=result)

        self.assertTrue(state.can_generate)
        metrics = build_metrics(result)
        self.assertTrue(any(metric.label == "Relecture MND" and metric.value == "OK" for metric in metrics))

    def test_release_scripts_audit_and_extract_changelog(self) -> None:
        root = Path(__file__).resolve().parents[1]
        audit = subprocess.run(
            [sys.executable, "scripts/audit_release_readiness.py", "--version", "0.1.0"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertIn("Préparation de mise en ligne OK", audit.stdout)

        changelog = subprocess.run(
            [sys.executable, "scripts/extract_changelog.py", "--version", "0.1.0"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(changelog.returncode, 0, changelog.stderr)
        self.assertIn("Conversion EmployeurD TXT vers MND MégaGest", changelog.stdout)

        with tempfile.TemporaryDirectory() as directory:
            version_output = Path(directory) / "version.txt"
            notes_output = Path(directory) / "notes.md"
            prepare = subprocess.run(
                [
                    sys.executable,
                    "scripts/prepare_release.py",
                    "--version",
                    "9.9.9",
                    "--dry-run",
                    "--version-output",
                    str(version_output),
                    "--release-notes-output",
                    str(notes_output),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            self.assertEqual(version_output.read_text(encoding="utf-8").strip(), "9.9.9")
            self.assertIn("Diff technique", notes_output.read_text(encoding="utf-8"))

    def test_virustotal_script_writes_local_report_without_api_key(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "EmployeurD-MegaGest.exe"
            executable.write_bytes(b"synthetic executable")
            report = Path(directory) / "virustotal.md"
            env = dict(os.environ)
            env.pop("VT_API_KEY", None)
            env.pop("VIRUSTOTAL_API_KEY", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/submit_virustotal.py",
                    "--file",
                    str(executable),
                    "--output",
                    str(report),
                    "--no-dotenv",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            report_text = report.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Soumis à VirusTotal : non", report_text)

    def test_virustotal_detection_collection_keeps_blocking_results(self) -> None:
        detections = collect_detections(
            {
                "CleanEngine": {"category": "undetected", "result": None},
                "MaliciousEngine": {"category": "malicious", "result": "Static AI"},
                "SuspiciousEngine": {"category": "suspicious", "result": "Packed"},
            }
        )

        self.assertEqual([item["engine"] for item in detections], ["MaliciousEngine", "SuspiciousEngine"])

    def test_virustotal_conflict_reads_existing_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "EmployeurD-MegaGest.exe"
            executable.write_bytes(b"synthetic executable")
            report = Path(directory) / "virustotal.md"
            argv = [
                "submit_virustotal.py",
                "--file",
                str(executable),
                "--output",
                str(report),
                "--api-key",
                "synthetic-key",
                "--fail-on-detections",
                "--no-dotenv",
            ]
            conflict = urllib.error.HTTPError("https://example.invalid/files", 409, "Conflict", {}, None)
            with (
                patch.object(sys, "argv", argv),
                patch("scripts.submit_virustotal.get_upload_url", return_value="https://example.invalid/files"),
                patch("scripts.submit_virustotal.post_file", side_effect=conflict),
                patch(
                    "scripts.submit_virustotal.get_file_report",
                    return_value={"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "suspicious": 0}}}},
                ),
            ):
                exit_code = submit_virustotal.main()

            report_text = report.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("Rapport VirusTotal existant consulté", report_text)

    def test_release_manifest_validates_hashes_and_clean_virustotal_report(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            dist = workdir / "dist"
            app = dist / "EmployeurD-MegaGest"
            app.mkdir(parents=True)
            executable = app / "EmployeurD-MegaGest.exe"
            portable = dist / "EmployeurD-MegaGest-v9.9.9-portable.zip"
            executable.write_bytes(b"synthetic executable")
            portable.write_bytes(b"synthetic portable zip")
            exe_sha = generate_release_manifest.sha256_file(executable)
            zip_sha = generate_release_manifest.sha256_file(portable)
            (dist / "EmployeurD-MegaGest-v9.9.9-portable.exe.sha256").write_text(
                f"{exe_sha}  EmployeurD-MegaGest.exe\n",
                encoding="ascii",
            )
            (dist / "EmployeurD-MegaGest-v9.9.9-portable.zip.sha256").write_text(
                f"{zip_sha}  EmployeurD-MegaGest-v9.9.9-portable.zip\n",
                encoding="ascii",
            )
            (dist / "EmployeurD-MegaGest-v9.9.9.virustotal.md").write_text(
                "\n".join(
                    [
                        "# Rapport VirusTotal",
                        "- Soumis à VirusTotal : oui",
                        "- Statut : terminé",
                        "- malicious : 0",
                        "- suspicious : 0",
                        "- Lien : https://www.virustotal.com/gui/file/synthetic",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts" / "generate_release_manifest.py"),
                    "--version",
                    "9.9.9",
                    "--require-clean-virustotal",
                ],
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
            )
            manifest = json.loads((dist / "EmployeurD-MegaGest-v9.9.9.release-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(manifest["artifacts"][0]["sha256"], zip_sha)
        self.assertEqual(manifest["artifacts"][1]["sha256"], exe_sha)
        self.assertFalse(manifest["privacy"]["payroll_files_submitted"])

    def test_release_manifest_blocks_virustotal_detections(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            dist = workdir / "dist"
            app = dist / "EmployeurD-MegaGest"
            app.mkdir(parents=True)
            executable = app / "EmployeurD-MegaGest.exe"
            portable = dist / "EmployeurD-MegaGest-v9.9.9-portable.zip"
            executable.write_bytes(b"synthetic executable")
            portable.write_bytes(b"synthetic portable zip")
            exe_sha = generate_release_manifest.sha256_file(executable)
            zip_sha = generate_release_manifest.sha256_file(portable)
            (dist / "EmployeurD-MegaGest-v9.9.9-portable.exe.sha256").write_text(f"{exe_sha}\n", encoding="ascii")
            (dist / "EmployeurD-MegaGest-v9.9.9-portable.zip.sha256").write_text(f"{zip_sha}\n", encoding="ascii")
            (dist / "EmployeurD-MegaGest-v9.9.9.virustotal.md").write_text(
                "- malicious : 1\n- suspicious : 0\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts" / "generate_release_manifest.py"),
                    "--version",
                    "9.9.9",
                    "--require-clean-virustotal",
                ],
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("VirusTotal", completed.stdout)

    def test_release_manifest_detects_unsigned_pe_without_powershell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "unsigned.exe"
            data = bytearray(512)
            data[0:2] = b"MZ"
            data[0x3C:0x40] = (0x80).to_bytes(4, "little")
            data[0x80:0x84] = b"PE\0\0"
            optional_header_offset = 0x80 + 24
            data[optional_header_offset : optional_header_offset + 2] = (0x20B).to_bytes(2, "little")
            executable.write_bytes(data)

            status = generate_release_manifest.pe_certificate_status(executable)

        self.assertEqual(status, "NotSigned")

    def test_release_notes_include_public_virustotal_score(self) -> None:
        section = append_release_verification.build_verification_section(
            {
                "distribution": {"signed": False, "authenticode_status": "NotSigned"},
                "artifacts": [
                    {"type": "portable_zip", "sha256": "zip-sha"},
                    {"type": "windows_executable_inside_zip", "sha256": "exe-sha"},
                ],
            },
            {
                "status": "completed",
                "malicious": 0,
                "suspicious": 0,
                "link": "https://www.virustotal.com/gui/file/example",
            },
            "EmployeurD-MegaGest-v9.9.9.virustotal.md",
        )

        self.assertIn("Score VirusTotal: `0 malicious / 0 suspicious`", section)
        self.assertIn("Rapport détaillé: `EmployeurD-MegaGest-v9.9.9.virustotal.md`", section)
        self.assertIn("SHA256 exécutable: `exe-sha`", section)
        self.assertIn("Données de paie transmises pendant cette vérification: `non`", section)


if __name__ == "__main__":
    unittest.main()

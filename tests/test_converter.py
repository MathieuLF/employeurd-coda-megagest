from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payroll_mnd_converter.converter import ConversionError, convert_file, load_mapping


class ConverterTest(unittest.TestCase):
    def test_convert_balanced_csv_to_fixed_width_file(self) -> None:
        root = Path(__file__).resolve().parents[1]
        mapping = load_mapping(root / "config" / "mapping.example.json")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mnd"
            result = convert_file(root / "samples" / "employeurd-example.csv", output, mapping)

            self.assertEqual(result.row_count, 3)
            self.assertEqual(result.total_debit, result.total_credit)
            output_bytes = output.read_bytes()
            self.assertTrue(output_bytes.endswith(b"\r\n"))
            self.assertNotIn(b"\r\r\n", output_bytes)

    def test_reject_unbalanced_entries(self) -> None:
        root = Path(__file__).resolve().parents[1]
        mapping = load_mapping(root / "config" / "mapping.example.json")

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "unbalanced.csv"
            source.write_text(
                "Date,Journal,Compte,Description,Reference,Debit,Credit\n"
                "2026-01-15,PA,5000-000,Salaires,PAIE-1,100.00,0.00\n",
                encoding="utf-8",
            )

            with self.assertRaises(ConversionError):
                convert_file(source, Path(directory) / "output.mnd", mapping)


if __name__ == "__main__":
    unittest.main()

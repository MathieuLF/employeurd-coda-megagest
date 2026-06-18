from __future__ import annotations

import argparse
from pathlib import Path

from .converter import ConversionError, convert_file, inspect_file, load_mapping


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="payroll-mnd-converter",
        description="Convertit un export de paie CSV/TXT en fichier texte .mnd selon un mapping.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Affiche les colonnes detectees dans un fichier source.")
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.add_argument("--encoding", default="utf-8-sig")

    convert_parser = subparsers.add_parser("convert", help="Convertit un fichier source en .mnd.")
    convert_parser.add_argument("input", type=Path)
    convert_parser.add_argument("output", type=Path)
    convert_parser.add_argument("--mapping", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect":
            result = inspect_file(args.input, encoding=args.encoding)
            print(f"colonnes={', '.join(result.columns)}")
            print(f"lignes={result.row_count}")
            return 0

        if args.command == "convert":
            mapping = load_mapping(args.mapping)
            result = convert_file(args.input, args.output, mapping)
            print(f"lignes={result.row_count}")
            print(f"debit={result.total_debit:.2f}")
            print(f"credit={result.total_credit:.2f}")
            print(f"sortie={args.output}")
            return 0

    except ConversionError as error:
        parser.exit(2, f"Erreur: {error}\n")

    parser.error("Commande inconnue.")
    return 2

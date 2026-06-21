from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def project_version(root: Path = ROOT) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("Version du projet introuvable dans pyproject.toml.")
    return version.strip()


def validation_commands(*, version: str, skip_release_audit: bool = False) -> list[list[str]]:
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        [sys.executable, "-X", "pycache_prefix=build/pycache", "-m", "compileall", "src", "scripts"],
    ]
    if not skip_release_audit:
        commands.append([sys.executable, "scripts/audit_release_readiness.py", "--version", version])
    return commands


def run_commands(commands: list[list[str]], *, root: Path = ROOT) -> int:
    for command in commands:
        print(f"> {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=root, check=False)
        if completed.returncode:
            return completed.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valide rapidement l'environnement local du dépôt.")
    parser.add_argument("--skip-release-audit", action="store_true", help="Ignore l'audit de préparation de release.")
    args = parser.parse_args(argv)
    version = project_version()
    return run_commands(validation_commands(version=version, skip_release_audit=args.skip_release_audit))


if __name__ == "__main__":
    raise SystemExit(main())

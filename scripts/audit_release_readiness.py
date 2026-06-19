from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path


SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(
        r"(?i)\b(vt_api_key|virustotal_api_key|api[_-]?key|client[_-]?secret|password|passwd|smtp_pass|refresh_token|access_token|private_key)\b"
        r"\s*[:=]\s*[\"']?[^\"'\s<>]{16,}[\"']?"
    ),
)

IGNORED_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "build", "dist", "outputs"}
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".lock",
    ".md",
    ".ps1",
    ".py",
    ".spec",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}
REQUIRED_GITIGNORE_PATTERNS = (
    ".env",
    ".env.*",
    "outputs/",
    "dist/",
    "build/",
    "*.mnd",
    "*.rapport.md",
    "*.validation.json",
)
BLOCKED_TRACKED_PATTERNS = (
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"(^|/)(outputs|logs|dist|build)/"),
    re.compile(r"\.(mnd|p12|pfx|pem|key)$", re.IGNORECASE),
    re.compile(r"\.(rapport\.md|validation\.json)$", re.IGNORECASE),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local avant une mise en ligne officielle.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    issues: list[str] = []

    issues.extend(_version_issues(root, args.version))
    issues.extend(_gitignore_issues(root))
    issues.extend(_tracked_file_issues(root))
    issues.extend(_secret_issues(root))
    if args.require_clean:
        issues.extend(_clean_tree_issues(root))

    if issues:
        print("Préparation de mise en ligne: problèmes à corriger", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    print(f"Préparation de mise en ligne OK pour v{args.version}")
    return 0


def _version_issues(root: Path, version: str) -> list[str]:
    issues: list[str] = []
    version_file = root / "src" / "employeurd_megagest" / "version.py"
    version_text = version_file.read_text(encoding="utf-8")
    if f'__version__ = "{version}"' not in version_text:
        issues.append(f"{version_file.relative_to(root)} ne déclare pas __version__ = \"{version}\".")

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject.get("project", {}).get("version")
    if project_version != version:
        issues.append(f"pyproject.toml déclare la version {project_version!r}, pas {version!r}.")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not _changelog_has_version(changelog, version):
        issues.append(f"CHANGELOG.md ne contient pas de section pour {version}.")
    return issues


def _gitignore_issues(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return [".gitignore est absent."]
    lines = {
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return [f".gitignore devrait contenir {pattern!r}." for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in lines]


def _tracked_file_issues(root: Path) -> list[str]:
    completed = _run_git(root, "ls-files")
    if completed.returncode != 0:
        return ["Impossible de lister les fichiers suivis par Git."]
    issues = []
    for raw_path in completed.stdout.splitlines():
        normalized = raw_path.replace("\\", "/")
        if any(pattern.search(normalized) for pattern in BLOCKED_TRACKED_PATTERNS):
            issues.append(f"Fichier sensible ou généré suivi par Git: {raw_path}")
    return issues


def _secret_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or _is_ignored_for_scan(root, path):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                issues.append(f"Secret potentiel: {path.relative_to(root)}:{line_number}")
    return issues


def _clean_tree_issues(root: Path) -> list[str]:
    completed = _run_git(root, "status", "--porcelain")
    if completed.returncode != 0:
        return ["Impossible de vérifier l'état Git."]
    if completed.stdout.strip():
        return ["Le dépôt doit être propre avant une mise en ligne officielle."]
    return []


def _changelog_has_version(changelog: str, version: str) -> bool:
    escaped = re.escape(version)
    return bool(re.search(rf"^##\s+(?:\[{escaped}\]|{escaped})(?:\s|$)", changelog, flags=re.MULTILINE))


def _is_ignored_for_scan(root: Path, path: Path) -> bool:
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        return True
    relative_parts = path.relative_to(root).parts
    return any(part in IGNORED_DIRS for part in relative_parts)


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())

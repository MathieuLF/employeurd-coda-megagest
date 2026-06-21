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

IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv-build",
    "__pycache__",
    "build",
    "dist",
    "interne",
    "logs",
    "notes-privees",
    "outputs",
    "venv",
    "ENV",
}
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
    "interne/",
    "secrets/",
    "credentials/",
    "notes-privees/",
    "outputs/",
    "logs/",
    "dist/",
    "build/",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.cer",
    "*.crt",
    "*.der",
    "*.mnd",
    "*.rapport.md",
    "*.validation.json",
    "*.security.local.md",
    "*.virustotal.local.md",
)
BLOCKED_TRACKED_PATTERNS = (
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"(^|/)interne/"),
    re.compile(r"(^|/)(outputs|logs|dist|build|secrets|credentials|notes-privees)/"),
    re.compile(r"(^|/)scripts/generate_icon\.ps1$"),
    re.compile(r"\.(mnd|p12|pfx|pem|key|cer|crt|der)$", re.IGNORECASE),
    re.compile(r"\.(rapport\.md|validation\.json)$", re.IGNORECASE),
    re.compile(r"\.(security|virustotal)\.local\.md$", re.IGNORECASE),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local avant une mise en ligne officielle.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    issues: list[str] = []

    issues.extend(_version_issues(root, args.version))
    issues.extend(_release_policy_issues(root))
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


def _release_policy_issues(root: Path) -> list[str]:
    issues: list[str] = []
    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")
    if "cx_Freeze" not in pyproject_text:
        issues.append("pyproject.toml doit déclarer cx_Freeze comme dépendance de build.")
    if "pyinstaller" in pyproject_text.lower():
        issues.append("pyproject.toml ne doit plus déclarer l'ancien packager pour la mise en ligne officielle.")

    build_script = (root / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
    if "cx_Freeze" not in build_script:
        issues.append("scripts/build_exe.ps1 doit utiliser cx_Freeze.")
    if "pyinstaller" in build_script.lower():
        issues.append("scripts/build_exe.ps1 ne doit pas utiliser l'ancien packager pour la mise en ligne officielle.")
    if "--icon" not in build_script or "EmployeurD-MegaGest.ico" not in build_script:
        issues.append("scripts/build_exe.ps1 doit intégrer l'icône produit Windows.")
    for asset in (
        root / "packaging" / "windows" / "EmployeurD-MegaGest.ico",
        root / "src" / "employeurd_megagest" / "assets" / "app-icon.png",
        root / "docs" / "assets" / "product-icon.png",
    ):
        if not asset.exists():
            issues.append(f"Asset d'icône produit manquant: {asset.relative_to(root)}")

    release_workflow = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    if re.search(r"(?m)^  push:\s*$", release_workflow):
        issues.append(".github/workflows/release.yml ne doit pas créer de brouillon automatiquement sur push de tag.")
    if "--fail-on-detections" not in release_workflow:
        issues.append(".github/workflows/release.yml doit bloquer les détections VirusTotal.")
    if '"dist/EmployeurD-MegaGest-v$env:RELEASE_VERSION-portable.zip"' not in release_workflow:
        issues.append(".github/workflows/release.yml doit publier le ZIP portable comme asset principal.")
    if "-portable.exe.sha256" not in release_workflow:
        issues.append(".github/workflows/release.yml doit publier l'empreinte de l'exécutable contenu dans le ZIP.")
    if "generate_release_manifest.py" not in release_workflow or ".release-manifest.json" not in release_workflow:
        issues.append(".github/workflows/release.yml doit générer et publier le manifeste de mise en ligne.")
    if "append_release_verification.py" not in release_workflow:
        issues.append(".github/workflows/release.yml doit afficher le score VirusTotal dans les notes de mise en ligne.")
    if re.search(r"(?m)^\s*\"dist/EmployeurD-MegaGest-v\$env:RELEASE_VERSION\.exe\"\s*`?$", release_workflow):
        issues.append(".github/workflows/release.yml ne doit pas publier de .exe direct sans certificat.")

    publish_script = (root / "scripts" / "publish_release.ps1").read_text(encoding="utf-8")
    if "generate_release_manifest.py" not in publish_script or ".release-manifest.json" not in publish_script:
        issues.append("scripts/publish_release.ps1 doit générer et joindre le manifeste de mise en ligne.")
    if "append_release_verification.py" not in publish_script:
        issues.append("scripts/publish_release.ps1 doit afficher le score VirusTotal dans les notes de mise en ligne.")
    if "$CreateGitHubRelease -and $AllowVirusTotalDetections" not in publish_script:
        issues.append("scripts/publish_release.ps1 doit empêcher une mise en ligne GitHub avec des détections VirusTotal ignorées.")
    if "Assert-NoExistingReleaseTarget" not in publish_script or "gh release view $Tag" not in publish_script:
        issues.append("scripts/publish_release.ps1 doit refuser une mise en ligne GitHub déjà existante.")
    if 'git ls-remote --tags origin "refs/tags/$Tag"' not in publish_script:
        issues.append("scripts/publish_release.ps1 doit refuser un tag distant déjà existant.")
    if "Assert-OfficialReleaseMainState" not in publish_script or '$Branch -ne "main"' not in publish_script:
        issues.append("scripts/publish_release.ps1 doit exiger main pour une mise en ligne officielle.")
    if "refs/remotes/origin/main" not in publish_script:
        issues.append("scripts/publish_release.ps1 doit vérifier que origin/main pointe sur HEAD.")
    if re.search(r"(?m)^\s*\"dist/\$Name-v\$ReleaseVersion\.exe\"\s*,?\s*$", publish_script):
        issues.append("scripts/publish_release.ps1 ne doit pas publier de .exe direct sans certificat.")

    return issues


def _tracked_file_issues(root: Path) -> list[str]:
    completed = _run_git(root, "ls-files")
    if completed.returncode != 0:
        return ["Impossible de lister les fichiers suivis par Git."]
    issues = []
    for raw_path in completed.stdout.splitlines():
        normalized = raw_path.replace("\\", "/")
        if normalized == ".env.example" or normalized.endswith(".example"):
            continue
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
    if any(part == ".venv" or part.startswith(".venv-") for part in relative_parts):
        return True
    return any(part in IGNORED_DIRS for part in relative_parts)


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())

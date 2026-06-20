from __future__ import annotations

import argparse
import re
import subprocess
from datetime import date
from pathlib import Path


VERSION_RE = re.compile(r'__version__ = "([^"]+)"')
PYPROJECT_VERSION_RE = re.compile(r'^version = "([^"]+)"$', re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prépare la version et les notes d'une mise en ligne.")
    parser.add_argument("--version", default="")
    parser.add_argument("--bump", choices=("patch", "minor", "major"), default="patch")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--change", action="append", default=[], help="Ligne du journal des changements à ajouter.")
    parser.add_argument("--write", action="store_true", help="Modifie les fichiers de version et le changelog.")
    parser.add_argument("--dry-run", action="store_true", help="Affiche la version sans modifier les fichiers.")
    parser.add_argument("--release-notes-output", default="")
    parser.add_argument("--version-output", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    current_version = read_current_version(root)
    version = args.version.strip() or bump_version(current_version, args.bump)

    changelog_path = root / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    new_changelog, notes = build_changelog(changelog, version, args.date, tuple(args.change), root)
    release_notes = build_release_notes(root, version, notes)

    if args.version_output:
        Path(args.version_output).write_text(version + "\n", encoding="utf-8")

    if args.release_notes_output:
        output = Path(args.release_notes_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(release_notes + "\n", encoding="utf-8")

    if args.write:
        write_version_files(root, version)
        changelog_path.write_text(new_changelog, encoding="utf-8")
    elif not args.dry_run:
        print(new_changelog)

    print(f"Version préparée: {version}")
    return 0


def read_current_version(root: Path) -> str:
    version_file = root / "src" / "employeurd_megagest" / "version.py"
    match = VERSION_RE.search(version_file.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("Version introuvable dans version.py.")
    return match.group(1)


def bump_version(version: str, bump: str) -> str:
    parts = [int(part) for part in version.split(".")]
    if len(parts) != 3:
        raise SystemExit(f"Version non conforme au format majeur.mineur.correctif: {version}")
    major, minor, patch = parts
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_version_files(root: Path, version: str) -> None:
    version_file = root / "src" / "employeurd_megagest" / "version.py"
    version_text = version_file.read_text(encoding="utf-8")
    version_file.write_text(VERSION_RE.sub(f'__version__ = "{version}"', version_text), encoding="utf-8")

    pyproject = root / "pyproject.toml"
    pyproject_text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(PYPROJECT_VERSION_RE.sub(f'version = "{version}"', pyproject_text), encoding="utf-8")


def build_changelog(changelog: str, version: str, release_date: str, changes: tuple[str, ...], root: Path) -> tuple[str, str]:
    if re.search(rf"^##\s+\[{re.escape(version)}\]", changelog, flags=re.MULTILINE):
        raise SystemExit(f"CHANGELOG.md contient déjà une section pour {version}.")

    heading = re.search(r"^##\s+\[Non publié\]\s*$", changelog, flags=re.MULTILINE)
    if not heading:
        raise SystemExit("CHANGELOG.md doit contenir une section ## [Non publié].")

    next_heading = re.search(r"^##\s+", changelog[heading.end() :], flags=re.MULTILINE)
    section_end = heading.end() + next_heading.start() if next_heading else len(changelog)
    before = changelog[: heading.end()]
    after = changelog[section_end:]

    existing = changelog[heading.end() : section_end].strip()
    notes = merge_notes(existing, changes, root)
    version_section = f"\n\n## [{version}] - {release_date}\n\n{notes}\n"
    new_changelog = before.rstrip() + "\n\n" + version_section.strip() + "\n" + after
    return new_changelog.rstrip() + "\n", notes


def merge_notes(existing: str, changes: tuple[str, ...], root: Path) -> str:
    lines = [line.rstrip() for line in existing.splitlines() if line.strip()]
    for change in changes:
        cleaned = change.strip()
        if cleaned:
            lines.append(cleaned if cleaned.startswith("- ") else f"- {cleaned}")
    if lines:
        return "\n".join(lines)
    return "\n".join(generated_change_lines(root))


def generated_change_lines(root: Path) -> list[str]:
    files = changed_files(root)
    if not files:
        return ["- Mise à jour de maintenance."]

    groups = {
        "Interface": ("app_gui.py", "gui_",),
        "Conversion": ("converter.py", "parser_", "writer_", "validator.py", "config/"),
        "Documentation": ("README", "docs/", "CONTRIBUTING", "SECURITY", "SUPPORT"),
        "Distribution": ("scripts/", "packaging/", ".github/", "CHANGELOG"),
        "Tests": ("tests/", "samples/"),
    }
    labels: list[str] = []
    for label, prefixes in groups.items():
        if any(any(part in file for part in prefixes) for file in files):
            labels.append(label.lower())
    if not labels:
        labels.append("maintenance")
    return [f"- Mise à jour {', '.join(labels)}."]


def build_release_notes(root: Path, version: str, notes: str) -> str:
    base = last_tag(root)
    commits = git_lines(root, "log", "--oneline", f"{base}..HEAD") if base else git_lines(root, "log", "--oneline", "-20")
    stat = git_lines(root, "diff", "--stat", f"{base}..HEAD") if base else git_lines(root, "diff", "--stat", "HEAD")
    if not stat:
        stat = git_lines(root, "diff", "--stat")

    lines = [
        f"# EmployeurD-MegaGest v{version}",
        "",
        "## Changements",
        "",
        notes,
        "",
        "## Diff technique",
        "",
        f"Base: `{base or 'historique local'}`",
        "",
    ]
    if commits:
        lines.extend(["### Commits", ""])
        lines.extend(f"- `{line}`" for line in commits[:30])
        lines.append("")
    if stat:
        lines.extend(["### Fichiers modifiés", "", "```text", *stat, "```"])
    else:
        lines.append("Aucun diff Git lisible au moment de la génération.")
    return "\n".join(lines).strip()


def changed_files(root: Path) -> list[str]:
    files = git_lines(root, "diff", "--name-only", "HEAD")
    if files:
        return files
    base = last_tag(root)
    return git_lines(root, "diff", "--name-only", f"{base}..HEAD") if base else []


def last_tag(root: Path) -> str:
    completed = run_git(root, "describe", "--tags", "--abbrev=0")
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_lines(root: Path, *args: str) -> list[str]:
    completed = run_git(root, *args)
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())

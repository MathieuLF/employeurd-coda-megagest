from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrait les notes d'une version depuis CHANGELOG.md.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--output", default="")
    parser.add_argument("--include-diff", action="store_true")
    args = parser.parse_args()

    changelog_path = Path(args.changelog)
    notes = extract_version_notes(changelog_path.read_text(encoding="utf-8"), args.version)
    if not notes:
        print(f"Aucune section du journal des changements trouvée pour {args.version}.", file=sys.stderr)
        return 1

    if args.include_diff:
        notes = notes + "\n\n" + build_diff_notes(changelog_path.resolve().parent)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(notes + "\n", encoding="utf-8")
    else:
        print(notes)
    return 0


def extract_version_notes(changelog: str, version: str) -> str:
    escaped = re.escape(version)
    heading = re.compile(rf"^##\s+(?:\[{escaped}\]|{escaped})(?:\s.*)?$", flags=re.MULTILINE)
    match = heading.search(changelog)
    if not match:
        return ""

    next_heading = re.search(r"^##\s+", changelog[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(changelog)
    section = changelog[match.end() : end].strip()
    return section


def build_diff_notes(root: Path) -> str:
    base = last_tag(root)
    commits = git_lines(root, "log", "--oneline", f"{base}..HEAD") if base else git_lines(root, "log", "--oneline", "-20")
    stat = git_lines(root, "diff", "--stat", f"{base}..HEAD") if base else git_lines(root, "diff", "--stat", "HEAD")
    if not stat:
        stat = git_lines(root, "diff", "--stat")

    lines = ["## Diff technique", "", f"Base: `{base or 'historique local'}`", ""]
    if commits:
        lines.extend(["### Commits", ""])
        lines.extend(f"- `{line}`" for line in commits[:30])
        lines.append("")
    if stat:
        lines.extend(["### Fichiers modifiés", "", "```text", *stat, "```"])
    else:
        lines.append("Aucun diff Git lisible au moment de la génération.")
    return "\n".join(lines)


def last_tag(root: Path) -> str:
    completed = run_git(root, "describe", "--tags", "--abbrev=0")
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_lines(root: Path, *args: str) -> list[str]:
    completed = run_git(root, *args)
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.generate_release_manifest import parse_virustotal_report
except ModuleNotFoundError:
    from generate_release_manifest import parse_virustotal_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Ajoute le résumé public de vérification aux notes de mise en ligne.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--virustotal-report", type=Path)
    args = parser.parse_args()

    version = args.version.strip().lstrip("v")
    name = "EmployeurD-MegaGest"
    notes_path = args.notes or Path("dist") / f"{name}-v{version}.release-notes.md"
    manifest_path = args.manifest or Path("dist") / f"{name}-v{version}.release-manifest.json"
    virustotal_path = args.virustotal_report or Path("dist") / f"{name}-v{version}.virustotal.md"

    if not notes_path.exists():
        print(f"Notes de mise en ligne introuvables: {notes_path}")
        return 1
    if not manifest_path.exists():
        print(f"Manifeste de mise en ligne introuvable: {manifest_path}")
        return 1
    if not virustotal_path.exists():
        print(f"Rapport VirusTotal introuvable: {virustotal_path}")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    virustotal = parse_virustotal_report(virustotal_path)
    section = build_verification_section(manifest, virustotal, virustotal_path.name)

    notes = notes_path.read_text(encoding="utf-8").rstrip()
    marker = "## Vérification publique"
    if marker in notes:
        notes = notes.split(marker, 1)[0].rstrip()
    notes_path.write_text(notes + "\n\n" + section + "\n", encoding="utf-8")
    print(notes_path)
    return 0


def build_verification_section(manifest: dict[str, Any], virustotal: dict[str, Any], report_name: str) -> str:
    artifacts = {artifact.get("type"): artifact for artifact in manifest.get("artifacts", [])}
    exe = artifacts.get("windows_executable_inside_zip", {})
    portable = artifacts.get("portable_zip", {})
    malicious = virustotal.get("malicious")
    suspicious = virustotal.get("suspicious")
    status = virustotal.get("status") or "n/d"
    link = virustotal.get("link") or ""
    signed = bool(manifest.get("distribution", {}).get("signed"))
    signature = manifest.get("distribution", {}).get("authenticode_status") or "n/d"

    lines = [
        "## Vérification publique",
        "",
        f"- Score VirusTotal: `{malicious} malicious / {suspicious} suspicious`.",
        f"- Statut VirusTotal: `{status}`.",
        f"- Rapport détaillé: `{report_name}`.",
        f"- SHA256 exécutable: `{exe.get('sha256', 'n/d')}`.",
        f"- SHA256 paquet portable: `{portable.get('sha256', 'n/d')}`.",
        f"- Signature Windows: `{'signé' if signed else signature}`.",
        "- Données de paie transmises pendant cette vérification: `non`.",
    ]
    if link:
        lines.insert(3, f"- Lien VirusTotal: {link}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

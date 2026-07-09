from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


API_ROOT = "https://www.virustotal.com/api/v3"
SMALL_FILE_LIMIT = 32 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description="Soumet l'exécutable public à VirusTotal et écrit un rapport Markdown.")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--wait-minutes", type=int, default=10)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--require-submit", action="store_true")
    parser.add_argument("--lookup-only", action="store_true", help="Consulte le rapport VirusTotal existant sans envoyer le fichier.")
    parser.add_argument("--no-dotenv", action="store_true", help="Ne charge pas le fichier .env local.")
    parser.add_argument("--fail-on-detections", action="store_true", help="Échoue si VirusTotal retourne une détection malicious ou suspicious.")
    args = parser.parse_args()

    if not args.no_dotenv:
        load_local_dotenv(Path(__file__).resolve().parents[1])
    api_key = args.api_key or os.environ.get("VT_API_KEY", "") or os.environ.get("VIRUSTOTAL_API_KEY", "")
    file_path = args.file
    sha256 = sha256_file(file_path)

    if not api_key:
        write_report(
            args.output,
            file_path=file_path,
            sha256=sha256,
            submitted=False,
            status="non soumis",
            message="Aucune clé VT_API_KEY ou VIRUSTOTAL_API_KEY n'est configurée.",
        )
        return 2 if args.require_submit else 0

    try:
        analysis_id = ""
        analysis: dict[str, Any] = {}
        already_present = False
        if not args.lookup_only:
            upload_url = get_upload_url(api_key) if file_path.stat().st_size >= SMALL_FILE_LIMIT else f"{API_ROOT}/files"
            try:
                upload_payload = post_file(upload_url, api_key, file_path)
                analysis_id = upload_payload.get("data", {}).get("id", "")
                analysis = poll_analysis(api_key, analysis_id, wait_minutes=args.wait_minutes, poll_seconds=args.poll_seconds) if analysis_id else {}
            except urllib.error.HTTPError as error:
                if error.code != 409:
                    raise
                already_present = True
        file_report = get_file_report(api_key, sha256)
    except Exception as error:
        write_report(
            args.output,
            file_path=file_path,
            sha256=sha256,
            submitted=not args.lookup_only,
            status="échec",
            message=str(error),
        )
        return 1 if args.require_submit else 0

    attributes = analysis.get("data", {}).get("attributes", {}) if isinstance(analysis, dict) else {}
    file_attributes = file_report.get("data", {}).get("attributes", {}) if isinstance(file_report, dict) else {}
    stats = attributes.get("stats") or file_attributes.get("last_analysis_stats", {})
    detections = collect_detections(file_attributes.get("last_analysis_results", {}))
    status = attributes.get("status") or ("rapport consulté" if args.lookup_only or already_present else "soumis")
    if args.lookup_only or already_present:
        message = "Rapport VirusTotal existant consulté."
    else:
        message = f"Analyse VirusTotal: {analysis_id or 'n/d'}"
    write_report(
        args.output,
        file_path=file_path,
        sha256=sha256,
        submitted=True,
        status=status,
        message=message,
        stats=stats if isinstance(stats, dict) else {},
        detections=detections,
    )
    if args.fail_on_detections and detections:
        return 4
    return 0


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_local_dotenv(root: Path) -> None:
    for path in (root / "interne" / ".env", root / ".env"):
        load_dotenv(path)


def get_upload_url(api_key: str) -> str:
    payload = vt_request(f"{API_ROOT}/files/upload_url", api_key)
    upload_url = payload.get("data")
    if not isinstance(upload_url, str) or not upload_url:
        raise RuntimeError("VirusTotal n'a pas retourné d'URL d'envoi.")
    return upload_url


def post_file(url: str, api_key: str, file_path: Path) -> dict[str, Any]:
    boundary = f"----emg-{uuid.uuid4().hex}"
    content = file_path.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("ascii"),
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode("utf-8"),
            b"Content-Type: application/octet-stream\r\n\r\n",
            content,
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        ]
    )
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "x-apikey": api_key,
        },
    )
    return open_json(request)


def poll_analysis(api_key: str, analysis_id: str, *, wait_minutes: int, poll_seconds: int) -> dict[str, Any]:
    deadline = time.time() + max(0, wait_minutes) * 60
    last_payload: dict[str, Any] = {}
    while time.time() <= deadline:
        last_payload = vt_request(f"{API_ROOT}/analyses/{analysis_id}", api_key)
        status = last_payload.get("data", {}).get("attributes", {}).get("status")
        if status and status not in {"queued", "in-progress"}:
            return last_payload
        time.sleep(max(1, poll_seconds))
    return last_payload


def get_file_report(api_key: str, sha256: str) -> dict[str, Any]:
    try:
        return vt_request(f"{API_ROOT}/files/{sha256}", api_key)
    except urllib.error.HTTPError:
        return {}


def vt_request(url: str, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "x-apikey": api_key})
    return open_json(request)


def collect_detections(results: Any) -> list[dict[str, str]]:
    if not isinstance(results, dict):
        return []
    detections: list[dict[str, str]] = []
    for engine, payload in sorted(results.items()):
        if not isinstance(payload, dict):
            continue
        category = str(payload.get("category", ""))
        if category not in {"malicious", "suspicious"}:
            continue
        detections.append(
            {
                "engine": str(engine),
                "category": category,
                "result": str(payload.get("result") or "n/d"),
            }
        )
    return detections


def open_json(request: urllib.request.Request) -> dict[str, Any]:
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Réponse VirusTotal inattendue.")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(
    path: Path,
    *,
    file_path: Path,
    sha256: str,
    submitted: bool,
    status: str,
    message: str,
    stats: dict[str, Any] | None = None,
    detections: list[dict[str, str]] | None = None,
) -> None:
    stats = stats or {}
    detections = detections or []
    lines = [
        f"# Rapport VirusTotal {file_path.name}",
        "",
        f"- Fichier : `{file_path.name}`",
        f"- SHA256 : `{sha256}`",
        f"- Soumis à VirusTotal : {'oui' if submitted else 'non'}",
        f"- Statut : {status}",
        f"- Message : {message}",
        f"- Lien : https://www.virustotal.com/gui/file/{sha256}",
    ]
    if stats:
        lines.extend(["", "## Résultat", ""])
        for key in ("malicious", "suspicious", "undetected", "harmless", "timeout", "failure"):
            if key in stats:
                lines.append(f"- {key} : {stats[key]}")
    if detections:
        lines.extend(["", "## Détections à examiner", ""])
        for detection in detections:
            lines.append(f"- {detection['engine']} : {detection['category']} / {detection['result']}")
    lines.extend(
        [
            "",
            "Ne jamais soumettre de fichiers TXT EmployeurD, rapports de contrôle, MND, Markdown ou JSON de validation.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

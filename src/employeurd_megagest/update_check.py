from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .version import APP_NAME, __version__


DEFAULT_UPDATE_URL = "https://api.github.com/repos/MathieuLF/employeurd-coda-megagest/releases/latest"


@dataclass(frozen=True)
class UpdateCheckResult:
    ok: bool
    update_available: bool
    current_version: str
    latest_version: str | None
    url: str
    download_url: str | None = None
    sha256: str | None = None
    published_at: str | None = None
    release_notes: str | None = None
    message: str = ""


def check_for_update(url: str, *, current_version: str = __version__, timeout: float = 5.0) -> UpdateCheckResult:
    resolved_url = configured_update_url(url)
    try:
        payload = _fetch_json(resolved_url, timeout=timeout)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return UpdateCheckResult(
                False,
                False,
                current_version,
                None,
                resolved_url,
                message="Aucune mise en ligne officielle n'est publiée pour le moment.",
            )
        return UpdateCheckResult(
            False,
            False,
            current_version,
            None,
            resolved_url,
            message=f"Vérification impossible pour le moment: HTTP {error.code}.",
        )
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        return UpdateCheckResult(
            False,
            False,
            current_version,
            None,
            resolved_url,
            message=f"Vérification impossible pour le moment: {error}",
        )

    latest = str(payload.get("latest_version") or payload.get("tag_name") or "").lstrip("v")
    if not latest:
        return UpdateCheckResult(
            False,
            False,
            current_version,
            None,
            resolved_url,
            message="La réponse de mise à jour est incomplète.",
        )
    update_available = _version_tuple(latest) > _version_tuple(current_version)
    return UpdateCheckResult(
        ok=True,
        update_available=update_available,
        current_version=current_version,
        latest_version=latest,
        url=resolved_url,
        download_url=payload.get("download_url") or payload.get("html_url"),
        sha256=payload.get("sha256"),
        published_at=payload.get("published_at") or payload.get("date"),
        release_notes=payload.get("release_notes") or payload.get("body"),
        message="Nouvelle version disponible." if update_available else "Application à jour.",
    )


def configured_update_url(url: str) -> str:
    cleaned = str(url or "").strip()
    if not cleaned or "<" in cleaned or ">" in cleaned:
        return DEFAULT_UPDATE_URL
    return cleaned


def _fetch_json(url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("JSON racine invalide", "", 0)
    return payload


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for part in value.strip().lstrip("v").split("."):
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)

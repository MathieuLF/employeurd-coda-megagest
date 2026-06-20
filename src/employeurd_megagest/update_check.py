from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .version import APP_NAME, __version__


DEFAULT_UPDATE_URL = "https://api.github.com/repos/MathieuLF/employeurd-coda-megagest/releases/latest"
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")


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
    download_url = (
        payload.get("download_url")
        or release_asset_url(payload, ".zip", version=latest)
        or release_asset_url(payload, ".exe", version=latest)
        or payload.get("html_url")
    )
    update_available = _version_tuple(latest) > _version_tuple(current_version)
    sha256 = extract_sha256(payload.get("sha256"))
    if not sha256:
        sha256 = _release_download_sha256(payload, download_url, version=latest, timeout=timeout)
    return UpdateCheckResult(
        ok=True,
        update_available=update_available,
        current_version=current_version,
        latest_version=latest,
        url=resolved_url,
        download_url=download_url,
        sha256=sha256,
        published_at=payload.get("published_at") or payload.get("date"),
        release_notes=payload.get("release_notes") or payload.get("body"),
        message="Nouvelle version disponible." if update_available else "Application à jour.",
    )


def configured_update_url(url: str) -> str:
    cleaned = str(url or "").strip()
    if not cleaned or "<" in cleaned or ">" in cleaned:
        return DEFAULT_UPDATE_URL
    return cleaned


def release_url_for_version(url: str, version: str) -> str:
    resolved = configured_update_url(url)
    if "/releases/latest" in resolved:
        return resolved.replace("/releases/latest", f"/releases/tags/v{version.strip().lstrip('v')}")
    return resolved


def release_asset_url(payload: dict[str, Any], suffix: str, *, version: str | None = None) -> str | None:
    asset = release_asset(payload, suffix, version=version)
    if not asset:
        return None
    value = asset.get("browser_download_url") or asset.get("url")
    return str(value) if value else None


def release_asset(payload: dict[str, Any], suffix: str, *, version: str | None = None) -> dict[str, Any] | None:
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None
    normalized_suffix = suffix.lower()
    normalized_version = (version or "").strip().lstrip("v")
    candidates: list[tuple[int, dict[str, Any]]] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        lowered_name = name.lower()
        if not lowered_name.endswith(normalized_suffix):
            continue
        score = 0
        if normalized_version and normalized_version in lowered_name:
            score += 2
        if "employeurd-megagest" in lowered_name:
            score += 1
        candidates.append((score, item))
    if not candidates:
        return None
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    return candidates[0][1]


def extract_sha256(value: object) -> str | None:
    match = SHA256_RE.search(str(value or ""))
    return match.group(0).lower() if match else None


def _release_download_sha256(
    payload: dict[str, Any],
    download_url: object,
    *,
    version: str,
    timeout: float,
) -> str | None:
    suffixes: list[str] = []
    lowered_download = str(download_url or "").lower()
    if lowered_download.endswith(".zip"):
        suffixes.append(".zip.sha256")
    if lowered_download.endswith(".exe"):
        suffixes.append(".exe.sha256")
    suffixes.extend([".zip.sha256", ".exe.sha256"])

    seen: set[str] = set()
    for suffix in suffixes:
        if suffix in seen:
            continue
        seen.add(suffix)
        sha256_url = release_asset_url(payload, suffix, version=version)
        if not sha256_url:
            continue
        try:
            found = extract_sha256(_fetch_text(sha256_url, timeout=timeout))
        except (OSError, urllib.error.URLError, TimeoutError):
            found = None
        if found:
            return found
    return None


def _fetch_json(url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("JSON racine invalide", "", 0)
    return payload


def _fetch_text(url: str, *, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    return data.decode("utf-8", errors="replace")


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for part in value.strip().lstrip("v").split("."):
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)

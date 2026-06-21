from __future__ import annotations

import json
import http.client
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .version import APP_NAME, __version__


DEFAULT_UPDATE_URL = "https://api.github.com/repos/MathieuLF/employeurd-coda-megagest/releases/latest"
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
GITHUB_API_RELEASE_RE = re.compile(r"^https://api\.github\.com/repos/([^/]+)/([^/]+)/releases(?:/latest|/tags/[^/?#]+)?")
GITHUB_WEB_RELEASE_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/releases")
GITHUB_RELEASE_TAG_RE = re.compile(r"/releases/tag/v?([0-9][0-9A-Za-z.\-_]*)")
DEFAULT_TIMEOUT_SECONDS = 1.25
DEFAULT_SHA256_TIMEOUT_SECONDS = 0.6
GITHUB_RELEASE_PAGE_BYTES = 0
TEMPORARY_HTTP_ERRORS = {502, 503, 504}
NETWORK_ERRORS = (OSError, urllib.error.URLError, TimeoutError, http.client.HTTPException, ValueError)


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
    release_page_url: str | None = None


@dataclass(frozen=True)
class _TextFetchResult:
    text: str
    final_url: str


def check_for_update(
    url: str,
    *,
    current_version: str = __version__,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    sha256_timeout: float = DEFAULT_SHA256_TIMEOUT_SECONDS,
) -> UpdateCheckResult:
    resolved_url = configured_update_url(url)
    github_payload = _fetch_github_release_page_payload(resolved_url, timeout=timeout)
    if github_payload:
        payload = github_payload
    elif _github_repo_from_url(resolved_url):
        return _failed_update_result(
            resolved_url,
            current_version,
            "Vérification impossible pour le moment: GitHub ne répond pas assez rapidement.",
        )
    else:
        payload_result = _fetch_json_payload_or_failure(resolved_url, current_version, timeout=timeout)
        if isinstance(payload_result, UpdateCheckResult):
            return payload_result
        payload = payload_result

    return _build_update_result(
        payload,
        resolved_url,
        current_version=current_version,
        sha256_timeout=sha256_timeout,
    )


def _fetch_json_payload_or_failure(url: str, current_version: str, *, timeout: float) -> dict[str, Any] | UpdateCheckResult:
    try:
        return _fetch_json(url, timeout=timeout)
    except urllib.error.HTTPError as error:
        message = _http_error_message(error)
        error.close()
        return _failed_update_result(url, current_version, message)
    except NETWORK_ERRORS as error:
        return _failed_update_result(url, current_version, _network_error_message(error))
    except json.JSONDecodeError as error:
        return _failed_update_result(url, current_version, _network_error_message(error))


def _build_update_result(
    payload: dict[str, Any],
    resolved_url: str,
    *,
    current_version: str,
    sha256_timeout: float,
) -> UpdateCheckResult:
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
    release_page_url = _release_page_url(payload, resolved_url, version=latest)
    download_url = payload.get("download_url") or release_asset_url(payload, ".zip", version=latest) or release_page_url
    update_available = _version_tuple(latest) > _version_tuple(current_version)
    sha256 = extract_sha256(payload.get("sha256"))
    if not sha256:
        sha256 = _release_download_sha256(payload, download_url, version=latest, timeout=sha256_timeout)
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
        release_page_url=release_page_url,
    )


def _failed_update_result(url: str, current_version: str, message: str) -> UpdateCheckResult:
    return UpdateCheckResult(False, False, current_version, None, url, message=message)


def _fetch_github_release_page_payload(url: str, *, timeout: float) -> dict[str, Any] | None:
    repo = _github_repo_from_url(url)
    if not repo:
        return None
    owner, name = repo
    latest_url = f"https://github.com/{owner}/{name}/releases/latest"
    try:
        response = _fetch_text_response(latest_url, timeout=timeout, max_bytes=GITHUB_RELEASE_PAGE_BYTES)
    except NETWORK_ERRORS:
        return None
    match = GITHUB_RELEASE_TAG_RE.search(response.final_url) or GITHUB_RELEASE_TAG_RE.search(response.text)
    if not match:
        return None
    version = match.group(1).strip().lstrip("v")
    if not version:
        return None
    release_url = f"https://github.com/{owner}/{name}/releases/tag/v{version}"
    download_root = f"https://github.com/{owner}/{name}/releases/download/v{version}"
    package_name = f"{APP_NAME}-v{version}-portable.zip"
    return {
        "tag_name": f"v{version}",
        "html_url": release_url,
        "assets": [
            {
                "name": package_name,
                "browser_download_url": f"{download_root}/{package_name}",
            },
            {
                "name": f"{package_name}.sha256",
                "browser_download_url": f"{download_root}/{package_name}.sha256",
            },
            {
                "name": f"{APP_NAME}-v{version}-portable.exe.sha256",
                "browser_download_url": f"{download_root}/{APP_NAME}-v{version}-portable.exe.sha256",
            },
        ],
    }


def _github_repo_from_url(url: str) -> tuple[str, str] | None:
    match = GITHUB_API_RELEASE_RE.match(url) or GITHUB_WEB_RELEASE_RE.match(url)
    if not match:
        return None
    return match.group(1), match.group(2)


def _http_error_message(error: urllib.error.HTTPError) -> str:
    if error.code == 404:
        return "Aucune mise en ligne officielle n'est publiée pour le moment."
    if error.code in TEMPORARY_HTTP_ERRORS:
        return f"Vérification impossible pour le moment: GitHub ne répond pas correctement (HTTP {error.code})."
    return f"Vérification impossible pour le moment: HTTP {error.code}."


def _network_error_message(error: BaseException) -> str:
    if isinstance(error, json.JSONDecodeError):
        return "La réponse de mise à jour est illisible pour le moment."
    if _is_timeout_error(error):
        return "Vérification impossible pour le moment: délai d'attente dépassé."
    if isinstance(error, urllib.error.URLError) and error.reason:
        reason = error.reason
        if isinstance(reason, BaseException) and _is_timeout_error(reason):
            return "Vérification impossible pour le moment: délai d'attente dépassé."
        return f"Vérification impossible pour le moment: {reason}."
    return f"Vérification impossible pour le moment: {error}."


def _is_timeout_error(error: BaseException | object) -> bool:
    if isinstance(error, TimeoutError):
        return True
    text = str(error).lower()
    return "timed out" in text or "timeout" in text or "délai d'attente" in text


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


def _release_page_url(payload: dict[str, Any], resolved_url: str, *, version: str) -> str | None:
    value = payload.get("html_url") or payload.get("release_page_url")
    if value:
        return str(value)
    repo = _github_repo_from_url(resolved_url)
    if repo:
        owner, name = repo
        cleaned_version = version.strip().lstrip("v")
        return f"https://github.com/{owner}/{name}/releases/tag/v{cleaned_version}"
    return None


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
    elif lowered_download.endswith(".exe"):
        suffixes.append(".exe.sha256")
    else:
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
        except NETWORK_ERRORS:
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
    return _fetch_text_response(url, timeout=timeout).text


def _fetch_text_response(url: str, *, timeout: float, max_bytes: int | None = None) -> _TextFetchResult:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(max_bytes) if max_bytes is not None else response.read()
        final_url = response.geturl()
    return _TextFetchResult(data.decode("utf-8", errors="replace"), final_url)


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for part in value.strip().lstrip("v").split("."):
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)

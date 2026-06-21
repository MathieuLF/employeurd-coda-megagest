from __future__ import annotations

import hashlib
import subprocess
import sys
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from .update_check import (
    DEFAULT_TIMEOUT_SECONDS,
    NETWORK_ERRORS,
    _fetch_json,
    _fetch_text,
    extract_sha256,
    release_asset_url,
    release_url_for_version,
)
from .version import __version__


SIGNATURE_TIMEOUT_SECONDS = 2


@dataclass(frozen=True)
class IntegrityCheckResult:
    status: str
    current_version: str
    executable_path: Path
    local_sha256: str | None
    expected_sha256: str | None
    signature_status: str
    release_url: str | None
    message: str

    @property
    def verified(self) -> bool:
        return self.status == "verified"


def local_integrity_details(*, executable_path: Path | None = None, current_version: str = __version__) -> IntegrityCheckResult:
    executable = Path(executable_path or sys.executable)
    local_sha256 = app_package_sha256(executable.parent) if _looks_like_frozen_app(executable) else sha256_file(executable)
    message = (
        "Empreinte locale de l'application calculée. La comparaison officielle n'a pas encore été lancée."
        if _looks_like_frozen_app(executable)
        else "Empreinte locale calculée. La comparaison officielle n'a pas encore été lancée."
    )
    return IntegrityCheckResult(
        status="local",
        current_version=current_version,
        executable_path=executable,
        local_sha256=local_sha256,
        expected_sha256=None,
        signature_status=signature_status(executable),
        release_url=None,
        message=message,
    )


def check_running_app_integrity(
    update_url: str,
    *,
    current_version: str = __version__,
    executable_path: Path | None = None,
    frozen: bool | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> IntegrityCheckResult:
    local = local_integrity_details(executable_path=executable_path, current_version=current_version)
    is_frozen = bool(getattr(sys, "frozen", False) if frozen is None else frozen)
    if not is_frozen:
        return _with_status(
            local,
            "source",
            "Version lancée depuis le code source. Aucune empreinte officielle d'exécutable n'est attendue.",
        )
    if not local.local_sha256:
        return _with_status(local, "unavailable", "Impossible de calculer l'empreinte de l'exécutable ouvert.")

    release_url = release_url_for_version(update_url, current_version)
    try:
        payload = _fetch_json(release_url, timeout=timeout)
    except urllib.error.HTTPError as error:
        status_code = error.code
        error.close()
        if status_code == 404:
            return _with_status(
                local,
                "unavailable",
                "Aucune version GitHub n'a été trouvée pour cette version.",
                release_url=release_url,
            )
        return _with_status(
            local,
            "unavailable",
            f"Vérification officielle impossible pour le moment : HTTP {status_code}.",
            release_url=release_url,
        )
    except NETWORK_ERRORS as error:
        return _with_status(
            local,
            "unavailable",
            f"Vérification officielle impossible pour le moment : {error}",
            release_url=release_url,
        )

    expected_kind = "package"
    expected = extract_sha256(payload.get("package_sha256"))
    if not expected:
        sha256_url = release_asset_url(payload, ".package.sha256", version=current_version)
        if sha256_url:
            try:
                expected = extract_sha256(_fetch_text(sha256_url, timeout=timeout))
            except NETWORK_ERRORS:
                expected = None
    if not expected:
        expected_kind = "exe"
        sha256_url = release_asset_url(payload, ".exe.sha256", version=current_version)
        if sha256_url:
            try:
                expected = extract_sha256(_fetch_text(sha256_url, timeout=timeout))
            except NETWORK_ERRORS:
                expected = None
    if not expected:
        return _with_status(
            local,
            "unavailable",
            "La version GitHub ne contient pas d'empreinte SHA256 lisible.",
            release_url=release_url,
        )

    actual = local.local_sha256 if expected_kind == "package" else sha256_file(local.executable_path)
    if actual and actual.lower() == expected.lower():
        return _with_status(
            local,
            "verified",
            "Version vérifiée. L'empreinte locale correspond à celle publiée sur GitHub.",
            expected_sha256=expected,
            release_url=release_url,
        )
    return _with_status(
        local,
        "mismatch",
        "Version inconnue ou modifiée. L'empreinte locale ne correspond pas à celle publiée sur GitHub.",
        expected_sha256=expected,
        release_url=release_url,
    )


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def app_package_sha256(root: Path) -> str | None:
    try:
        files = sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and not path.name.lower().endswith(".package.sha256")
        )
    except OSError:
        return None
    if not files:
        return None

    digest = hashlib.sha256()
    for path in files:
        try:
            relative = path.relative_to(root).as_posix().lower()
        except ValueError:
            return None
        file_hash = sha256_file(path)
        if not file_hash:
            return None
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _looks_like_frozen_app(executable: Path) -> bool:
    return (executable.parent / "lib" / "library.zip").exists()


def signature_status(path: Path) -> str:
    if not sys.platform.startswith("win"):
        return "Non applicable"
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-AuthenticodeSignature -LiteralPath {str(path)!r}).Status",
            ],
            capture_output=True,
            text=True,
            timeout=SIGNATURE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Non vérifiée"
    status = completed.stdout.strip()
    return status or "Non vérifiée"


def _with_status(
    result: IntegrityCheckResult,
    status: str,
    message: str,
    *,
    expected_sha256: str | None = None,
    release_url: str | None = None,
) -> IntegrityCheckResult:
    return IntegrityCheckResult(
        status=status,
        current_version=result.current_version,
        executable_path=result.executable_path,
        local_sha256=result.local_sha256,
        expected_sha256=expected_sha256,
        signature_status=result.signature_status,
        release_url=release_url,
        message=message,
    )

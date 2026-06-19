from __future__ import annotations

import hashlib
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk

from .audit_log import default_log_dir
from .gui_state import summary_text
from .gui_texts import LEGAL_NOTICE_TEXT, SECURITY_NOTICE_TEXT, SUPPORT_EMAIL, SUPPORT_ISSUE_URL, Text
from .models import ConversionResult
from .platform_actions import open_folder, open_path
from .update_check import UpdateCheckResult
from .version import __version__


def show_legal_notice(parent: tk.Tk) -> None:
    dialog = _dialog(parent, "Mentions légales", "680x460")
    _text_block(dialog, LEGAL_NOTICE_TEXT).grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 10))
    _button_row(dialog, [(Text.close, dialog.destroy)])


def show_support_window(parent: tk.Tk) -> None:
    dialog = _dialog(parent, "Support", "680x420")
    content = "\n".join(
        [
            "Besoin d'aide?",
            "=============",
            "",
            "Pour un problème reproductible ou une amélioration, privilégiez l'ouverture d'un billet GitHub. C'est le meilleur endroit pour suivre la demande et conserver le contexte.",
            "",
            f"Courriel : {SUPPORT_EMAIL}",
            "",
            "Important",
            "=========",
            "",
            "Ne joignez jamais de fichier de paie réel, de rapport SPD réel, de MND réel, de rapport Markdown, de JSON de validation ou de capture contenant des données sensibles.",
            "",
            "Pour aider au diagnostic, indiquez seulement la version de l'application, l'étape concernée et le message affiché.",
        ]
    )
    text = _text_block(dialog, content)
    text.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 10))
    _button_row(
        dialog,
        [
            ("Ouvrir un billet GitHub", lambda: webbrowser.open(SUPPORT_ISSUE_URL)),
            ("Écrire un courriel", lambda: webbrowser.open(f"mailto:{SUPPORT_EMAIL}")),
            (Text.close, dialog.destroy),
        ],
    )


def show_report_preview(parent: tk.Tk, result: ConversionResult | None) -> None:
    dialog = _dialog(parent, "Résumé de vérification", "760x560")
    content = _report_text(result)
    text = _text_block(dialog, content)
    text.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 10))
    actions = [
        (Text.copy_summary, lambda: _copy(parent, content)),
    ]
    if result and result.report_path:
        actions.append((Text.open_markdown, lambda: open_path(result.report_path)))
    if result and (result.output_path or result.report_path):
        target = result.output_path or result.report_path
        if target:
            actions.append((Text.open_folder, lambda: open_folder(target)))
    actions.append((Text.close, dialog.destroy))
    _button_row(dialog, actions)


def show_security_window(
    parent: tk.Tk,
    *,
    update_check_on_startup: bool,
    on_toggle_startup,
) -> None:
    dialog = _dialog(parent, "Sécurité", "720x520")
    text = _text_block(dialog, _security_intro_text())
    text.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 10))

    check_var = tk.BooleanVar(value=update_check_on_startup)
    check = ttk.Checkbutton(
        dialog,
        text="Vérifier les mises à jour au démarrage",
        variable=check_var,
        command=lambda: on_toggle_startup(check_var.get()),
    )
    check.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

    _button_row(dialog, [("Ouvrir les logs", lambda: open_folder(default_log_dir())), (Text.close, dialog.destroy)], row=2)
    _load_security_details(dialog, text)


def show_update_result(parent: tk.Tk, result: UpdateCheckResult) -> None:
    dialog = _dialog(parent, "Mise à jour", "620x420")
    body = [
        f"Version installée : {result.current_version}",
        f"Dernière version : {result.latest_version or 'n/d'}",
        f"Date : {result.published_at or 'n/d'}",
        f"État : {result.message}",
        f"SHA256 attendu : {result.sha256 or 'n/d'}",
        "",
        "Aucun fichier de paie n'a été transmis pendant cette vérification.",
    ]
    if result.release_notes:
        body.extend(["", "Notes de version", "================", result.release_notes])
    if not result.ok:
        body.append("L'utilitaire demeure utilisable hors ligne.")
    text = _text_block(dialog, "\n".join(body))
    text.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 10))
    actions = []
    if result.download_url:
        actions.append(("Ouvrir la mise en ligne", lambda: webbrowser.open(result.download_url or "")))
    actions.append((Text.close, dialog.destroy))
    _button_row(dialog, actions)


def _dialog(parent: tk.Tk, title: str, geometry: str) -> tk.Toplevel:
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.geometry(geometry)
    dialog.minsize(520, 360)
    dialog.configure(background="#f3f6fa")
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(0, weight=1)
    return dialog


def _text_block(parent: tk.Widget, content: str) -> tk.Text:
    text = tk.Text(parent, wrap="word", padx=16, pady=14, borderwidth=0, font=("Segoe UI", 10))
    text.insert("1.0", content)
    text.configure(state="disabled")
    return text


def _button_row(parent: tk.Toplevel, actions: list[tuple[str, object]], *, row: int = 1) -> None:
    frame = ttk.Frame(parent)
    frame.grid(row=row, column=0, sticky="e", padx=16, pady=(0, 16))
    for index, (label, command) in enumerate(actions):
        ttk.Button(frame, text=label, command=command).grid(row=0, column=index, padx=(8 if index else 0, 0))


def _copy(parent: tk.Tk, value: str) -> None:
    parent.clipboard_clear()
    parent.clipboard_append(value)


def _report_text(result: ConversionResult | None) -> str:
    if not result:
        return "Aucune validation n'a encore été lancée."
    lines = [
        "Résumé",
        "======",
        summary_text(result),
        "",
        "Fichiers",
        "========",
        f"Source : {result.source_path.name}",
        f"MND : {result.output_path or 'non généré'}",
        f"Rapport : {result.report_path or 'non généré'}",
        f"JSON : {result.validation_json_path or 'non généré'}",
        "",
        "Empreintes",
        "==========",
        f"SHA256 source : {result.source_sha256 or 'n/d'}",
        f"SHA256 MND : {result.mnd_sha256 or 'n/d'}",
        "",
        "Messages",
        "========",
    ]
    lines.extend(f"- {message.message}" for message in result.messages)
    if not result.messages:
        lines.append("- Aucun message bloquant.")
    return "\n".join(lines)


def _security_intro_text() -> str:
    return "\n".join(
        [
            f"Version : {__version__}",
            "",
            SECURITY_NOTICE_TEXT,
            "",
            "Informations de l'exécutable",
            "============================",
            "Calcul en cours... La fenêtre demeure utilisable pendant la vérification.",
        ]
    )


def _load_security_details(dialog: tk.Toplevel, text: tk.Text) -> None:
    result_queue: queue.Queue[str] = queue.Queue()

    def worker() -> None:
        result_queue.put(_security_details_text())

    def poll() -> None:
        try:
            details = result_queue.get_nowait()
        except queue.Empty:
            if dialog.winfo_exists():
                dialog.after(75, poll)
            return
        if dialog.winfo_exists():
            _replace_text(text, _security_intro_text().replace("Calcul en cours... La fenêtre demeure utilisable pendant la vérification.", details))

    threading.Thread(target=worker, daemon=True).start()
    dialog.after(75, poll)


def _security_details_text() -> str:
    executable = Path(sys.executable)
    lines = [
        f"Exécutable : {executable.name}",
        f"SHA256 exécutable : {_sha256_file(executable) or 'n/d'}",
        f"Signature : {_signature_status(executable)}",
    ]
    return "\n".join(lines)


def _replace_text(widget: tk.Text, value: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", value)
    widget.configure(state="disabled")


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _signature_status(path: Path) -> str:
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
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Non vérifiée"
    status = completed.stdout.strip()
    return status or "Non vérifiée"

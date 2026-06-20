from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Palette:
    background = "#f5f5f5"
    surface = "#ffffff"
    surface_alt = "#fafafa"
    surface_hover = "#f3f8ff"
    header = "#ffffff"
    header_muted = "#5f6b7a"
    text = "#1f1f1f"
    muted = "#616161"
    border = "#e0e0e0"
    border_strong = "#c7c7c7"
    primary = "#0f6cbd"
    primary_hover = "#115ea3"
    primary_pressed = "#0f548c"
    primary_dark = "#0b4a7a"
    success = "#107c10"
    success_bg = "#f1faf1"
    warning = "#8a5a00"
    warning_bg = "#fff8e1"
    danger = "#c50f1f"
    danger_bg = "#fdf3f4"
    info_bg = "#eef6fc"
    disabled = "#a19f9d"
    disabled_bg = "#f3f2f1"
    focus = "#005fb8"


def configure_theme(root: tk.Tk) -> None:
    root.configure(background=Palette.background)
    root.option_add("*Font", ("Segoe UI", 10))

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", font=("Segoe UI", 10), background=Palette.background, foreground=Palette.text)
    style.configure("App.TFrame", background=Palette.background)
    style.configure("ActionBar.TFrame", background=Palette.surface, relief="flat", borderwidth=0)
    style.configure("Card.TFrame", background=Palette.surface, relief="flat", borderwidth=0)
    style.configure("CardBody.TFrame", background=Palette.surface)
    style.configure("CardAlt.TFrame", background=Palette.surface_alt)
    style.configure("SectionRail.TFrame", background=Palette.primary)
    style.configure("Header.TFrame", background=Palette.header)
    style.configure("HeaderTitle.TLabel", background=Palette.header, foreground=Palette.text, font=("Segoe UI Semibold", 16))
    style.configure("HeaderMeta.TLabel", background=Palette.header, foreground=Palette.header_muted, font=("Segoe UI", 10))
    style.configure("HeaderBadge.TLabel", background=Palette.info_bg, foreground=Palette.primary_dark, font=("Segoe UI Semibold", 9), padding=(9, 4))
    style.configure("Title.TLabel", background=Palette.surface, foreground=Palette.text, font=("Segoe UI Semibold", 10))
    style.configure("RequiredBadge.TLabel", background=Palette.danger_bg, foreground=Palette.danger, font=("Segoe UI Semibold", 8), padding=(8, 3))
    style.configure("OptionalBadge.TLabel", background=Palette.info_bg, foreground=Palette.primary_dark, font=("Segoe UI Semibold", 8), padding=(8, 3))
    style.configure("Body.TLabel", background=Palette.surface, foreground=Palette.text)
    style.configure("HintInfo.TLabel", background=Palette.info_bg, foreground=Palette.primary_dark, font=("Segoe UI", 9), padding=(10, 7))
    style.configure("HintSuccess.TLabel", background=Palette.success_bg, foreground=Palette.success, font=("Segoe UI", 9), padding=(10, 7))
    style.configure("HintWarning.TLabel", background=Palette.warning_bg, foreground=Palette.warning, font=("Segoe UI", 9), padding=(10, 7))
    style.configure("Muted.TLabel", background=Palette.surface, foreground=Palette.muted)
    style.configure("SmallMuted.TLabel", background=Palette.surface, foreground=Palette.muted, font=("Segoe UI", 9))
    style.configure("Footer.TLabel", background=Palette.background, foreground=Palette.muted, font=("Segoe UI", 9))
    style.configure("SurfaceFooter.TLabel", background=Palette.surface, foreground=Palette.muted, font=("Segoe UI", 9))
    style.configure("Link.TLabel", background=Palette.background, foreground=Palette.primary, font=("Segoe UI Semibold", 9))
    style.configure("CardLink.TLabel", background=Palette.surface, foreground=Palette.primary, font=("Segoe UI Semibold", 9))
    style.configure("StatusTitle.TLabel", background=Palette.surface, foreground=Palette.text, font=("Segoe UI Semibold", 14))
    style.configure("PanelEyebrow.TLabel", background=Palette.surface, foreground=Palette.primary_dark, font=("Segoe UI Semibold", 9))
    style.configure("StepBadge.TLabel", background=Palette.info_bg, foreground=Palette.primary_dark, font=("Segoe UI Semibold", 10), padding=(9, 5))
    style.configure(
        "Primary.TButton",
        font=("Segoe UI Semibold", 10),
        padding=(15, 8),
        background=Palette.primary,
        foreground="#ffffff",
        bordercolor=Palette.primary,
        lightcolor=Palette.primary,
        darkcolor=Palette.primary,
        focusthickness=1,
        focuscolor=Palette.focus,
    )
    style.configure(
        "Action.TButton",
        padding=(12, 7),
        background=Palette.surface,
        foreground=Palette.text,
        bordercolor=Palette.border_strong,
        lightcolor=Palette.surface,
        darkcolor=Palette.border,
        focusthickness=1,
        focuscolor=Palette.focus,
    )
    style.configure(
        "Quiet.TButton",
        padding=(11, 7),
        background=Palette.surface_alt,
        foreground=Palette.text,
        bordercolor=Palette.border,
        lightcolor=Palette.surface_alt,
        darkcolor=Palette.border,
        focusthickness=1,
        focuscolor=Palette.focus,
    )
    style.map(
        "Primary.TButton",
        background=[
            ("disabled", Palette.disabled_bg),
            ("pressed", Palette.primary_pressed),
            ("active", Palette.primary_hover),
            ("!disabled", Palette.primary),
        ],
        foreground=[("disabled", Palette.disabled), ("!disabled", "#ffffff")],
        bordercolor=[("disabled", Palette.disabled_bg), ("!disabled", Palette.primary)],
    )
    style.map(
        "Action.TButton",
        background=[("disabled", Palette.disabled_bg), ("pressed", "#e8f1fb"), ("active", Palette.surface_hover), ("!disabled", Palette.surface)],
        foreground=[("disabled", Palette.disabled), ("!disabled", Palette.text)],
        bordercolor=[("active", Palette.primary), ("!disabled", Palette.border_strong)],
    )
    style.map(
        "Quiet.TButton",
        background=[("disabled", Palette.disabled_bg), ("pressed", "#ededed"), ("active", "#f7f7f7"), ("!disabled", Palette.surface_alt)],
        foreground=[("disabled", Palette.disabled), ("!disabled", Palette.text)],
    )
    style.configure(
        "TEntry",
        padding=(7, 6),
        fieldbackground=Palette.surface,
        bordercolor=Palette.border_strong,
        lightcolor=Palette.surface,
        darkcolor=Palette.border,
        insertcolor=Palette.text,
    )
    style.map("TEntry", bordercolor=[("focus", Palette.primary), ("!disabled", Palette.border_strong)])
    style.configure("TCheckbutton", background=Palette.surface, foreground=Palette.text, focuscolor=Palette.focus)
    style.map("TCheckbutton", foreground=[("disabled", Palette.disabled), ("!disabled", Palette.text)])
    style.configure("Horizontal.TProgressbar", troughcolor="#e5e5e5", background=Palette.primary)
    style.configure("Vertical.TScrollbar", troughcolor=Palette.background, background=Palette.border, arrowcolor=Palette.muted)
    style.configure("TNotebook", background=Palette.surface, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(12, 6), font=("Segoe UI Semibold", 9))
    style.map("TNotebook.Tab", foreground=[("selected", Palette.primary_dark), ("!selected", Palette.muted)])


def status_colors(status: str) -> tuple[str, str]:
    if status == "success":
        return Palette.success_bg, Palette.success
    if status == "warning":
        return Palette.warning_bg, Palette.warning
    if status == "error":
        return Palette.danger_bg, Palette.danger
    return Palette.info_bg, Palette.primary

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Palette:
    background = "#f5f7f8"
    surface = "#ffffff"
    surface_alt = "#f8fafb"
    header = "#ffffff"
    header_muted = "#52606d"
    text = "#1f2937"
    muted = "#4b5563"
    border = "#d8dee4"
    primary = "#0f766e"
    primary_dark = "#115e59"
    success = "#157347"
    success_bg = "#e6f4ea"
    warning = "#8a5a00"
    warning_bg = "#fff4cf"
    danger = "#b42318"
    danger_bg = "#fde8e7"
    info_bg = "#e6f3f1"
    disabled = "#9aa5b1"


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
    style.configure("Body.TLabel", background=Palette.surface, foreground=Palette.text)
    style.configure("Muted.TLabel", background=Palette.surface, foreground=Palette.muted)
    style.configure("SmallMuted.TLabel", background=Palette.surface, foreground=Palette.muted, font=("Segoe UI", 9))
    style.configure("Footer.TLabel", background=Palette.background, foreground=Palette.muted, font=("Segoe UI", 9))
    style.configure("SurfaceFooter.TLabel", background=Palette.surface, foreground=Palette.muted, font=("Segoe UI", 9))
    style.configure("Link.TLabel", background=Palette.background, foreground=Palette.primary, font=("Segoe UI Semibold", 9))
    style.configure("CardLink.TLabel", background=Palette.surface, foreground=Palette.primary, font=("Segoe UI Semibold", 9))
    style.configure("StatusTitle.TLabel", background=Palette.surface, foreground=Palette.text, font=("Segoe UI Semibold", 11))
    style.configure("PanelEyebrow.TLabel", background=Palette.surface, foreground=Palette.primary_dark, font=("Segoe UI Semibold", 9))
    style.configure("StepBadge.TLabel", background=Palette.info_bg, foreground=Palette.primary_dark, font=("Segoe UI Semibold", 9), padding=(7, 3))
    style.configure("Primary.TButton", font=("Segoe UI Semibold", 10), padding=(14, 8))
    style.configure("Action.TButton", padding=(10, 7))
    style.configure("Quiet.TButton", padding=(9, 6))
    style.map("Primary.TButton", background=[("active", Palette.primary_dark), ("!disabled", Palette.primary)], foreground=[("!disabled", "#ffffff")])
    style.configure("TEntry", padding=(6, 5))
    style.configure("Horizontal.TProgressbar", troughcolor="#e4e7ec", background=Palette.primary)
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

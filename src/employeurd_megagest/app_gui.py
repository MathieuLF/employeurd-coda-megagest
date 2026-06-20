from __future__ import annotations

import queue
import tempfile
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import load_app_config
from .errors import ConfigurationError, ConversionError, ValidationFailed
from .gui_controller import GuiController, GuiOperationResult
from .gui_dialogs import show_legal_notice, show_report_preview, show_security_window, show_support_window, show_update_result
from .gui_state import (
    build_file_preview,
    build_output_preview,
    default_output_root,
    generated_files,
)
from .gui_texts import (
    APP_DISPLAY_NAME,
    APP_SUBTITLE,
    COPYRIGHT_TEXT,
    REPOSITORY_LINK_TEXT,
    REPOSITORY_URL,
    Text,
    WEBSITE_LINK_TEXT,
    WEBSITE_URL,
)
from .gui_theme import Palette, configure_theme, status_colors
from .platform_actions import open_folder
from .preferences import load_preferences, remember_output_dir, remember_update_check_on_startup
from .resource_paths import default_config_dir, package_asset_path
from .update_check import UpdateCheckResult, check_for_update
from .user_messages import friendly_error_message, technical_error_message
from .version import __version__


_STATUS_ICON_CACHE: dict[str, tk.PhotoImage] | None = None


def _status_icon_images() -> dict[str, tk.PhotoImage]:
    global _STATUS_ICON_CACHE
    if _STATUS_ICON_CACHE is not None:
        return _STATUS_ICON_CACHE

    icons: dict[str, tk.PhotoImage] = {}
    for name in ("check", "shield", "warning", "error", "dot"):
        path = package_asset_path(f"status-{name}.png")
        if not path.exists():
            continue
        try:
            icons[name] = tk.PhotoImage(file=str(path))
        except tk.TclError:
            continue
    _STATUS_ICON_CACHE = icons
    return icons


class ModernScrollbar(tk.Canvas):
    def __init__(self, parent: tk.Widget, *, command) -> None:
        super().__init__(
            parent,
            width=14,
            highlightthickness=0,
            borderwidth=0,
            background=Palette.background,
            cursor="sb_v_double_arrow",
        )
        self.command = command
        self.first = 0.0
        self.last = 1.0
        self._thumb: tuple[float, float] = (0.0, 0.0)
        self._drag_offset = 0.0
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)

    def set(self, first: str, last: str) -> None:
        self.first = max(0.0, min(1.0, float(first)))
        self.last = max(self.first, min(1.0, float(last)))
        visible = max(0.0, min(1.0, self.last - self.first))
        if self.first <= 0.02 and visible >= 0.98:
            self.grid_remove()
        else:
            self.grid()
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        height = max(1, self.winfo_height())
        pad = 10
        x = 7
        track_top = pad
        track_bottom = max(pad + 1, height - pad)
        track_height = track_bottom - track_top
        self.create_line(x, track_top, x, track_bottom, fill=Palette.border, width=5, capstyle=tk.ROUND)

        visible = max(0.05, min(1.0, self.last - self.first))
        thumb_height = max(44, track_height * visible)
        max_travel = max(0.0, track_height - thumb_height)
        start_fraction = self.first / max(0.001, 1.0 - visible) if visible < 1.0 else 0.0
        thumb_top = track_top + (max_travel * min(1.0, start_fraction))
        thumb_bottom = min(track_bottom, thumb_top + thumb_height)
        self._thumb = (thumb_top, thumb_bottom)
        color = Palette.primary if visible < 1.0 else "#cbd5e1"
        self.create_line(x, thumb_top, x, thumb_bottom, fill=color, width=6, capstyle=tk.ROUND)

    def _on_press(self, event) -> None:
        top, bottom = self._thumb
        if top <= event.y <= bottom:
            self._drag_offset = event.y - top
            return
        direction = -1 if event.y < top else 1
        self.command("scroll", direction, "pages")

    def _on_drag(self, event) -> None:
        visible = max(0.05, min(1.0, self.last - self.first))
        if visible >= 1.0:
            return
        height = max(1, self.winfo_height())
        pad = 10
        track_height = max(1, height - (pad * 2))
        thumb_height = max(44, track_height * visible)
        max_travel = max(1.0, track_height - thumb_height)
        y = min(max(event.y - self._drag_offset, pad), pad + max_travel)
        fraction = (y - pad) / max_travel
        self.command("moveto", fraction * (1.0 - visible))


class StatusBadge(tk.Frame):
    def __init__(self, parent: tk.Widget, text: str, *, icon: str = "dot") -> None:
        super().__init__(
            parent,
            bd=0,
            background=Palette.header,
        )
        self._text = text
        self._icon = icon
        self._bg, self._fg = status_colors("info")
        self._font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self._icons = _status_icon_images()
        self._icon_label = tk.Label(self, background=self._bg, bd=0)
        self._icon_label.grid(row=0, column=0, padx=(9, 5), pady=5)
        self._label = tk.Label(self, text=self._text, background=self._bg, foreground=self._fg, font=self._font, bd=0)
        self._label.grid(row=0, column=1, padx=(0, 10), pady=5)
        self._redraw()

    def configure(self, cnf=None, **kwargs):  # noqa: ANN001
        if cnf:
            kwargs.update(cnf)
        text = kwargs.pop("text", None)
        icon = kwargs.pop("icon", None)
        background = kwargs.pop("background", None)
        foreground = kwargs.pop("foreground", None)
        if text is not None:
            self._text = str(text)
        if icon is not None:
            self._icon = str(icon)
        if background is not None:
            self._bg = str(background)
        if foreground is not None:
            self._fg = str(foreground)
        if kwargs:
            super().configure(**kwargs)
        self._redraw()

    config = configure

    def _redraw(self) -> None:
        super().configure(background=self._bg)
        self._icon_label.configure(background=self._bg)
        self._label.configure(text=self._text, background=self._bg, foreground=self._fg)
        image = self._icons.get(self._icon) or self._icons.get("dot")
        if image:
            self._icon_label.configure(image=image, text="", width=18, height=18)
            self._icon_label.image = image
        else:
            self._icon_label.configure(image="", text="●", foreground=self._fg, font=self._font, width=2)


class CheckOption(tk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        text: str,
        variable: tk.BooleanVar,
        command=None,
        description: str = "",
    ) -> None:
        super().__init__(
            parent,
            bd=0,
            background=Palette.surface,
            highlightbackground=Palette.border,
            highlightcolor=Palette.border,
            highlightthickness=1,
            padx=10,
            pady=8,
            cursor="hand2",
        )
        self.variable = variable
        self.command = command
        self._disabled = False
        self.columnconfigure(1, weight=1)

        self._box = tk.Canvas(self, width=19, height=19, highlightthickness=0, borderwidth=0, background=Palette.surface, cursor="hand2")
        self._box.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 8), pady=(1, 0))
        self._title = tk.Label(
            self,
            text=text,
            background=Palette.surface,
            foreground=Palette.text,
            font=("Segoe UI Semibold", 9),
            anchor="w",
            justify="left",
            cursor="hand2",
        )
        self._title.grid(row=0, column=1, sticky="ew")
        self._description = tk.Label(
            self,
            text=description,
            background=Palette.surface,
            foreground=Palette.muted,
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
            wraplength=220,
            cursor="hand2",
        )
        if description:
            self._description.grid(row=1, column=1, sticky="ew", pady=(1, 0))

        for widget in (self, self._box, self._title, self._description):
            widget.bind("<Button-1>", self._toggle)
        self.variable.trace_add("write", lambda *_: self._redraw())
        self._redraw()

    def state(self, states: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if "disabled" in states:
            self._disabled = True
        if "!disabled" in states:
            self._disabled = False
        self._redraw()
        return ("disabled",) if self._disabled else ()

    def _toggle(self, _event=None) -> None:
        if self._disabled:
            return
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def _redraw(self) -> None:
        checked = self.variable.get()
        bg = Palette.disabled_bg if self._disabled else Palette.info_bg if checked else Palette.surface
        border = Palette.disabled_bg if self._disabled else Palette.primary if checked else Palette.border
        fg = Palette.disabled if self._disabled else Palette.text
        muted = Palette.disabled if self._disabled else Palette.muted
        cursor = "arrow" if self._disabled else "hand2"

        self.configure(background=bg, highlightbackground=border, cursor=cursor)
        self._box.configure(background=bg, cursor=cursor)
        self._title.configure(background=bg, foreground=fg, cursor=cursor)
        self._description.configure(background=bg, foreground=muted, cursor=cursor)

        self._box.delete("all")
        outline = Palette.disabled if self._disabled else Palette.primary if checked else Palette.border_strong
        fill = Palette.primary if checked and not self._disabled else Palette.surface
        self._box.create_rectangle(2, 2, 17, 17, fill=fill, outline=outline, width=1)
        if checked:
            color = "#ffffff" if not self._disabled else Palette.disabled
            self._box.create_line(6, 10, 9, 13, 14, 6, fill=color, width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget, *, padding: tuple[int, int, int, int]) -> None:
        super().__init__(parent, style="App.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._mouse_inside = False

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=Palette.background)
        self.scrollbar = ModernScrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.content = ttk.Frame(self.canvas, style="App.TFrame", padding=padding)
        self._window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda _event: self._set_mouse_inside(True))
        self.canvas.bind("<Leave>", lambda _event: self._set_mouse_inside(False))
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _set_mouse_inside(self, inside: bool) -> None:
        self._mouse_inside = inside

    def _on_content_configure(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if not self._mouse_inside:
            return
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 * int(event.delta / 120)
        self.canvas.yview_scroll(delta, "units")


class EmployeurDMegaGestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"EmployeurD-MegaGest {__version__}")
        self._set_initial_geometry()
        self._set_product_icon()

        self.controller = GuiController(config_dir=default_config_dir())
        self.preferences = load_preferences()
        self.source_path = tk.StringVar()
        self.spd640_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=_usable_saved_output_dir(self.preferences.output_dir))
        self.require_spd640 = tk.BooleanVar(value=False)
        self.write_report_md = tk.BooleanVar(value=False)
        self.write_validation_json = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Prêt à commencer")
        self.status_detail = tk.StringVar(value="Ajoutez l'écriture EmployeurD. Sans dossier choisi, la sortie ira dans Documents.")
        self.update_status = tk.StringVar(value="Mise à jour non vérifiée")
        self.disabled_reason = tk.StringVar(value="")
        self.last_result: GuiOperationResult | None = None
        self.last_error: Exception | None = None
        self.last_update_result: UpdateCheckResult | None = None
        self.busy = False
        self.activity_log: list[str] = [_timestamped("Ouverture de l'application. Ajoutez l'écriture EmployeurD pour commencer.")]
        self._task_queue: queue.Queue[tuple[bool, object]] = queue.Queue()
        self._task_on_success = None

        configure_theme(self)
        self._build_ui()
        self._bind_shortcuts()
        self._refresh_all()

        if self.preferences.update_check_on_startup:
            self.after(750, lambda: self._check_update(show_dialog=False))

    def _set_product_icon(self) -> None:
        icon_paths = [
            package_asset_path("app-icon-16.png"),
            package_asset_path("app-icon-32.png"),
            package_asset_path("app-icon-48.png"),
            package_asset_path("app-icon.png"),
        ]
        try:
            self._window_icons = [tk.PhotoImage(file=str(path)) for path in icon_paths if path.exists()]
            if self._window_icons:
                self.iconphoto(True, *self._window_icons)
            header_path = package_asset_path("app-icon-40.png")
            fallback_path = package_asset_path("app-icon-48.png")
            if header_path.exists():
                self._header_icon = tk.PhotoImage(file=str(header_path))
            elif fallback_path.exists():
                self._header_icon = tk.PhotoImage(file=str(fallback_path))
        except tk.TclError:
            pass

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_header().grid(row=0, column=0, sticky="ew")
        self.scroll_area = ScrollableFrame(self, padding=(16, 14, 16, 10))
        self.scroll_area.grid(row=1, column=0, sticky="nsew")
        body = self.scroll_area.content
        body.columnconfigure(0, weight=7)
        body.columnconfigure(1, weight=5)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)
        self._build_inputs_card(left).grid(row=0, column=0, sticky="ew", pady=(0, 9))
        self._build_validation_card(left).grid(row=1, column=0, sticky="ew", pady=(0, 9))
        self._build_output_card(left).grid(row=2, column=0, sticky="ew")

        right = ttk.Frame(body, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self._build_dashboard_card(right).grid(row=0, column=0, sticky="nsew")

        self._build_action_bar().grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._build_footer().grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 10))

        for variable in (self.source_path, self.spd640_path):
            variable.trace_add("write", lambda *_: self._mark_dirty())
        self.output_dir.trace_add("write", lambda *_: self._refresh_all())

    def _build_header(self) -> ttk.Frame:
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        header.columnconfigure(0, weight=1)
        brand = ttk.Frame(header, style="Header.TFrame")
        brand.grid(row=0, column=0, sticky="w")
        brand.columnconfigure(1, weight=1)
        if hasattr(self, "_header_icon"):
            tk.Label(brand, image=self._header_icon, background=Palette.header, bd=0).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(brand, text=APP_DISPLAY_NAME, style="HeaderTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(
            brand,
            text=APP_SUBTITLE,
            style="HeaderMeta.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(3, 0))

        badges = ttk.Frame(header, style="Header.TFrame")
        badges.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(14, 0))
        self.status_badge = _badge_label(badges, "Prêt")
        self.security_badge = _badge_label(badges, "Sécurité")
        self.update_badge = _badge_label(badges, "Version")
        self.status_badge.grid(row=0, column=0, padx=(0, 8))
        self.security_badge.grid(row=0, column=1, padx=(0, 8))
        self.update_badge.grid(row=0, column=2)
        return header

    def _build_inputs_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = _card(parent)
        _card_title(card, "1", "Fichiers EmployeurD", "Ajoutez le TXT de paie. Un rapport de contrôle peut compléter la vérification.").grid(row=0, column=0, columnspan=3, sticky="ew")
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Écriture détaillée EmployeurD (TXT) · obligatoire", style="Title.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 1))
        ttk.Label(
            card,
            text="Fichier obligatoire à convertir en MND.",
            style="SmallMuted.TLabel",
            wraplength=430,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 2))
        ttk.Entry(card, textvariable=self.source_path).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        self.source_button = ttk.Button(card, text=Text.choose, command=self._choose_source, style="Action.TButton")
        self.source_button.grid(row=3, column=2, sticky="e", padx=(10, 0), pady=(3, 0))
        self.source_meta = ttk.Label(card, text="", style="SmallMuted.TLabel", wraplength=430, justify="left")
        self.source_meta.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        ttk.Separator(card).grid(row=5, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(card, text="Rapport de contrôle (CSV ou XML) · facultatif", style="Title.TLabel").grid(row=6, column=0, columnspan=3, sticky="w")
        ttk.Label(
            card,
            text="SPD640-P confirme les débits/crédits. SPD681 contrôle les écarts RRQ/AE/RQAP.",
            style="SmallMuted.TLabel",
            wraplength=430,
            justify="left",
        ).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(1, 2))
        ttk.Entry(card, textvariable=self.spd640_path).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        spd_actions = ttk.Frame(card, style="CardBody.TFrame")
        spd_actions.grid(row=8, column=2, sticky="e", padx=(10, 0), pady=(5, 0))
        self.spd640_button = ttk.Button(spd_actions, text=Text.choose, command=self._choose_spd640, style="Action.TButton")
        self.spd640_button.grid(row=0, column=0, padx=(0, 6))
        self.clear_spd640_button = ttk.Button(spd_actions, text=Text.remove, command=self._clear_spd640, style="Quiet.TButton")
        self.clear_spd640_button.grid(row=0, column=1)
        self.spd640_meta = ttk.Label(card, text="", style="SmallMuted.TLabel", wraplength=430, justify="left")
        self.spd640_meta.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        return card

    def _build_validation_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = _card(parent)
        _card_title(card, "2", "Concordance", "Avec un rapport de contrôle, vous pouvez bloquer la création si un contrôle échoue.").grid(row=0, column=0, sticky="ew")
        self.validation_mode_label = ttk.Label(card, text="", style="Body.TLabel", wraplength=430, justify="left")
        self.validation_mode_label.grid(row=1, column=0, sticky="ew", pady=(6, 5))
        self.require_spd640_check = CheckOption(
            card,
            variable=self.require_spd640,
            command=self._mark_dirty,
            text="Exiger la concordance du rapport",
            description="Si un contrôle obligatoire échoue, le MND ne sera pas créé.",
        )
        self.require_spd640_check.grid(row=2, column=0, sticky="ew", pady=(2, 0))
        return card

    def _build_output_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = _card(parent)
        _card_title(card, "3", "Destination", "Choisissez le dossier parent. L'application créera le sous-dossier horodaté.").grid(row=0, column=0, columnspan=3, sticky="ew")
        card.columnconfigure(0, weight=1)
        ttk.Entry(card, textvariable=self.output_dir).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.output_button = ttk.Button(card, text=Text.choose, command=self._choose_output_dir, style="Action.TButton")
        self.output_button.grid(row=1, column=2, sticky="e", padx=(10, 0), pady=(8, 0))
        self.output_meta = ttk.Label(card, text="", style="SmallMuted.TLabel", wraplength=430, justify="left")
        self.output_meta.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        self.output_files = ttk.Label(card, text="", style="SmallMuted.TLabel", wraplength=430, justify="left")
        self.output_files.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        options = ttk.Frame(card, style="CardBody.TFrame")
        options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        options.columnconfigure(0, weight=1)
        options.columnconfigure(1, weight=1)
        self.report_option = CheckOption(
            options,
            variable=self.write_report_md,
            text="Rapport Markdown (.md)",
            description="Résumé lisible de la vérification.",
            command=self._refresh_all,
        )
        self.report_option.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.json_option = CheckOption(
            options,
            variable=self.write_validation_json,
            text="Validation JSON (.json)",
            description="Détails structurés pour audit ou support.",
            command=self._refresh_all,
        )
        self.json_option.grid(row=0, column=1, sticky="ew")
        return card

    def _build_dashboard_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = _card(parent)
        card.rowconfigure(4, weight=1)
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text="Journal de traitement", style="PanelEyebrow.TLabel").grid(row=0, column=0, sticky="w")
        tk.Label(
            card,
            textvariable=self.status,
            background=Palette.surface,
            foreground=Palette.text,
            font=("Segoe UI Semibold", 13),
            anchor="w",
            justify="left",
            wraplength=390,
        ).grid(row=1, column=0, sticky="ew", pady=(7, 1))
        tk.Label(
            card,
            textvariable=self.status_detail,
            background=Palette.surface,
            foreground=Palette.muted,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=390,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 7))
        self.progress = ttk.Progressbar(card, mode="indeterminate")
        self.progress.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.progress.grid_remove()

        journal_panel = _subpanel(card)
        journal_panel.grid(row=4, column=0, sticky="nsew")
        journal_panel.rowconfigure(1, weight=1)
        journal_panel.columnconfigure(0, weight=1)
        _panel_title(journal_panel, "Journal").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.log_text = _dashboard_text(journal_panel, height=18, font_size=9)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        return card

    def _build_action_bar(self) -> ttk.Frame:
        bar = tk.Frame(
            self,
            background=Palette.surface,
            highlightbackground=Palette.border,
            highlightcolor=Palette.border,
            highlightthickness=1,
            bd=0,
            padx=14,
            pady=11,
        )
        bar.columnconfigure(1, weight=1)
        primary = ttk.Frame(bar, style="CardBody.TFrame")
        primary.grid(row=0, column=0, sticky="w")
        self.validate_button = ttk.Button(primary, text=Text.validate_payroll, command=self._validate, style="Primary.TButton")
        self.generate_button = ttk.Button(primary, text=Text.generate_mnd, command=self._generate, style="Action.TButton")
        self.validate_button.grid(row=0, column=0, padx=(0, 8))
        self.generate_button.grid(row=0, column=1)

        reason = ttk.Label(bar, textvariable=self.disabled_reason, style="SurfaceFooter.TLabel", wraplength=340, justify="left")
        reason.grid(row=0, column=1, sticky="w", padx=14)

        secondary = ttk.Frame(bar, style="CardBody.TFrame")
        secondary.grid(row=0, column=2, sticky="e")
        self.report_button = ttk.Button(secondary, text=Text.open_report, command=self._show_report, style="Action.TButton")
        self.folder_button = ttk.Button(secondary, text=Text.open_folder, command=self._open_folder, style="Action.TButton")
        self.report_button.grid(row=0, column=0, padx=(0, 8))
        self.folder_button.grid(row=0, column=1)
        return bar

    def _build_footer(self) -> ttk.Frame:
        footer = ttk.Frame(self, style="App.TFrame")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text=COPYRIGHT_TEXT, style="Footer.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.update_status, style="Footer.TLabel").grid(row=0, column=1, sticky="e", padx=(0, 18))
        links = ttk.Frame(footer, style="App.TFrame")
        links.grid(row=0, column=2, sticky="e")
        _link_label(links, Text.legal, lambda: show_legal_notice(self)).grid(row=0, column=0, padx=(0, 12))
        _link_label(links, WEBSITE_LINK_TEXT, lambda: webbrowser.open(WEBSITE_URL)).grid(row=0, column=1, padx=(0, 12))
        _link_label(links, REPOSITORY_LINK_TEXT, lambda: webbrowser.open(REPOSITORY_URL)).grid(row=0, column=2, padx=(0, 12))
        _link_label(links, Text.security, self._show_security).grid(row=0, column=3, padx=(0, 12))
        _link_label(links, Text.support, self._show_support).grid(row=0, column=4, padx=(0, 12))
        self.update_button = ttk.Button(links, text=Text.check_updates, command=lambda: self._check_update(show_dialog=True), style="Quiet.TButton")
        self.update_button.grid(row=0, column=5)
        return footer

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-o>", lambda _event: self._choose_source())
        self.bind_all("<Control-O>", lambda _event: self._choose_source())
        self.bind_all("<Control-r>", lambda _event: self._show_report())
        self.bind_all("<Control-R>", lambda _event: self._show_report())
        self.bind_all("<Control-g>", lambda _event: self._generate())
        self.bind_all("<Control-G>", lambda _event: self._generate())
        self.bind_all("<F5>", lambda _event: self._check_update(show_dialog=True))

    def _choose_source(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choisir l'écriture détaillée standard EmployeurD",
            filetypes=[("Fichiers texte", "*.txt *.TXT"), ("Tous les fichiers", "*.*")],
        )
        if selected:
            self.source_path.set(selected)
            self._log_event(f"Écriture sélectionnée : {Path(selected).name}")

    def _choose_spd640(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choisir un rapport de contrôle",
            filetypes=[("Rapports de contrôle", "*.csv *.CSV *.xml *.XML"), ("Tous les fichiers", "*.*")],
        )
        if selected:
            self.spd640_path.set(selected)
            self.require_spd640.set(_control_report_kind(selected) == "SPD640-P")
            self._log_event(f"Rapport de contrôle sélectionné : {Path(selected).name}")
            self._refresh_all()

    def _clear_spd640(self) -> None:
        self.spd640_path.set("")
        self.require_spd640.set(False)
        self._log_event("Rapport de contrôle retiré.")
        self._mark_dirty()

    def _choose_output_dir(self) -> None:
        initial_dir = self.output_dir.get().strip() or str(default_output_root())
        selected = filedialog.askdirectory(title="Choisir un dossier de sortie", initialdir=initial_dir)
        if selected:
            self.output_dir.set(selected)
            self._remember_output_dir(selected)
            self._log_event("Dossier de sortie sélectionné.")

    def _validate(self) -> None:
        if self.busy:
            return
        try:
            self._validate_inputs()
        except (ConfigurationError, ConversionError, OSError, ValidationFailed) as error:
            self._show_error(error)
            self._refresh_all()
            return

        source_path = Path(self.source_path.get())
        spd640_path = _optional_path(self.spd640_path.get())
        require_spd640 = self.require_spd640.get()
        self._run_background(
            "Validation en cours",
            lambda: self.controller.validate(
                source_path=source_path,
                spd640_path=spd640_path,
                require_spd640=require_spd640,
            ),
            self._validation_succeeded,
        )

    def _generate(self) -> None:
        if self.busy or not self._can_generate():
            return
        try:
            self._validate_inputs()
        except (ConfigurationError, ConversionError, OSError, ValidationFailed) as error:
            self._show_error(error)
            self._refresh_all()
            return

        source_path = Path(self.source_path.get())
        output_root = self._resolved_output_root()
        spd640_path = _optional_path(self.spd640_path.get())
        require_spd640 = self.require_spd640.get()
        write_report = self.write_report_md.get()
        write_validation_json = self.write_validation_json.get()
        self._run_background(
            "Génération en cours",
            lambda: self.controller.generate(
                source_path=source_path,
                output_root=output_root,
                spd640_path=spd640_path,
                require_spd640=require_spd640,
                write_report=write_report,
                write_validation_json=write_validation_json,
            ),
            self._generation_succeeded,
        )

    def _run_background(self, title: str, worker, on_success) -> None:
        self.busy = True
        self._task_on_success = on_success
        self.status.set(title)
        self.status_detail.set("L'application vérifie les fichiers sur cet ordinateur.")
        self._refresh_all()
        self.progress.start(12)

        def target() -> None:
            try:
                result = worker()
            except Exception as error:  # marshalled to the Tk thread below
                self._task_queue.put((False, error))
            else:
                self._task_queue.put((True, result))

        threading.Thread(target=target, daemon=True).start()
        self.after(50, self._poll_task_queue)

    def _poll_task_queue(self) -> None:
        try:
            ok, payload = self._task_queue.get_nowait()
        except queue.Empty:
            if self.busy:
                self.after(50, self._poll_task_queue)
            return
        if ok:
            assert self._task_on_success is not None
            self._operation_succeeded(payload, self._task_on_success)
        else:
            assert isinstance(payload, Exception)
            self._operation_failed(payload)

    def _operation_succeeded(self, result: GuiOperationResult | UpdateCheckResult, on_success) -> None:
        self.busy = False
        self._task_on_success = None
        self.progress.stop()
        self.last_error = None
        on_success(result)
        self._refresh_all()

    def _operation_failed(self, error: Exception) -> None:
        self.busy = False
        self._task_on_success = None
        self.progress.stop()
        self._show_error(error)
        self._refresh_all()

    def _validation_succeeded(self, result: GuiOperationResult) -> None:
        self.last_result = result
        self.status.set("Validation réussie")
        self.status_detail.set("Tout est prêt. Vous pouvez créer le fichier MND.")
        self._log_event("Vérification réussie. Création du MND disponible.")

    def _generation_succeeded(self, result: GuiOperationResult) -> None:
        self._remember_output_dir(self.output_dir.get())
        self.last_result = result
        self.status.set("MND créé")
        self.status_detail.set(_generated_outputs_status(result))
        self._log_event(_generated_outputs_log(result))
        messagebox.showinfo("Conversion terminée", _generated_outputs_message(result))

    def _show_error(self, error: Exception) -> None:
        self.last_result = None
        self.last_error = error
        self.status.set("À corriger")
        self.status_detail.set("Aucun MND ne sera créé tant que le problème n'est pas réglé.")
        self._log_event("Problème à corriger. Création du MND désactivée.")
        messagebox.showerror(
            "À corriger avant de créer le MND",
            f"{friendly_error_message(error)}\n\nDétails à transmettre au support:\n{technical_error_message(error)}",
        )

    def _show_report(self) -> None:
        if self.last_result:
            show_report_preview(self, self.last_result.conversion)

    def _open_folder(self) -> None:
        if self.last_result and self.last_result.conversion:
            files = generated_files(self.last_result.conversion)
            if files:
                open_folder(files[0])
                return
        output = self._resolved_output_root()
        if output.exists():
            open_folder(output)

    def _show_security(self) -> None:
        config = load_app_config(default_config_dir())
        show_security_window(
            self,
            update_check_on_startup=self.preferences.update_check_on_startup,
            update_url=str(config.updates.get("url", "")),
            on_toggle_startup=self._set_update_check_on_startup,
        )

    def _show_support(self) -> None:
        show_support_window(self)

    def _check_update(self, *, show_dialog: bool) -> None:
        if self.busy:
            return
        config = load_app_config(default_config_dir())
        update_url = str(config.updates.get("url", ""))
        self.update_status.set("Vérification de mise à jour...")
        self.update_button.configure(text=Text.check_updates)
        self.update_button.state(["disabled"])
        self._refresh_update_badge()
        result_queue: queue.Queue[UpdateCheckResult] = queue.Queue()

        def worker() -> None:
            result_queue.put(check_for_update(update_url))

        def poll() -> None:
            try:
                result = result_queue.get_nowait()
            except queue.Empty:
                if self.winfo_exists():
                    self.after(100, poll)
                return
            if self.winfo_exists():
                self.update_button.state(["!disabled"])
                self._update_check_finished(result, show_dialog=show_dialog)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _update_check_finished(self, result: UpdateCheckResult, *, show_dialog: bool) -> None:
        self.last_update_result = result
        if result.update_available:
            self.status.set("Mise à jour disponible")
            self.status_detail.set("Une nouvelle version est disponible. Rien ne sera installé automatiquement.")
            self.update_status.set(f"Nouvelle version : {result.latest_version}")
            self.update_button.configure(text=Text.update_available)
            self._log_event("Mise à jour disponible.")
        elif result.ok:
            self.update_status.set("Application à jour")
            self.update_button.configure(text=Text.up_to_date)
            self._log_event("Vérification terminée : application à jour.")
        else:
            self.update_status.set("Mise à jour non vérifiée")
            self.update_button.configure(text=Text.check_updates)
            self._log_event("Vérification de mise à jour impossible. L'application demeure utilisable.")
        self._refresh_update_badge()
        if show_dialog:
            show_update_result(self, result)

    def _validate_inputs(self) -> None:
        source = self.source_path.get().strip()
        if not source:
            raise ConversionError("Ajoutez l'écriture EmployeurD à convertir.")
        source_preview = build_file_preview(source, label="EmployeurD", suffixes=(".txt",), optional=False)
        if not source_preview.ok:
            raise ConversionError(source_preview.detail)
        output_preview = build_output_preview(
            source,
            self.output_dir.get(),
            include_report=self.write_report_md.get(),
            include_validation_json=self.write_validation_json.get(),
        )
        if not output_preview.ok:
            raise ConversionError(output_preview.detail)
        if self.require_spd640.get() and not self.spd640_path.get().strip():
            raise ValidationFailed("Le rapport de contrôle est requis en mode bloquant.")

    def _mark_dirty(self) -> None:
        if self.busy:
            return
        self.last_result = None
        self.last_error = None
        self.status.set("Vérification à refaire")
        self.status_detail.set("Les choix ont changé. Vérifiez de nouveau avant de créer le MND.")
        self._refresh_all()

    def _refresh_all(self) -> None:
        source_preview = build_file_preview(self.source_path.get(), label="EmployeurD", suffixes=(".txt",), optional=False)
        spd_preview = build_file_preview(self.spd640_path.get(), label="Rapport de contrôle", suffixes=(".csv", ".xml"), optional=True)
        output_preview = build_output_preview(
            self.source_path.get(),
            self.output_dir.get(),
            include_report=self.write_report_md.get(),
            include_validation_json=self.write_validation_json.get(),
        )

        _set_optional_label(self.source_meta, _file_preview_text(source_preview))
        _set_optional_label(self.spd640_meta, _file_preview_text(spd_preview))
        self.output_meta.configure(text=output_preview.detail)
        self.output_files.configure(text=_output_files_text(output_preview.files))

        has_spd640 = bool(self.spd640_path.get().strip())
        if not has_spd640 and self.require_spd640.get():
            self.require_spd640.set(False)
        self.require_spd640_check.state(["!disabled"] if has_spd640 and not self.busy else ["disabled"])
        self.clear_spd640_button.state(["!disabled"] if has_spd640 and not self.busy else ["disabled"])

        can_validate = self._can_validate()
        can_generate = self._can_generate()
        self.validate_button.state(["!disabled"] if can_validate else ["disabled"])
        self.generate_button.state(["!disabled"] if can_generate else ["disabled"])
        self.validate_button.configure(style="Action.TButton" if can_generate else "Primary.TButton")
        self.generate_button.configure(style="Primary.TButton" if can_generate else "Action.TButton")
        self.report_button.state(["!disabled"] if self.last_result else ["disabled"])
        folder_available = bool(generated_files(self.last_result.conversion) if self.last_result and self.last_result.conversion else False) or self._resolved_output_root().exists()
        self.folder_button.state(["!disabled"] if folder_available and not self.busy else ["disabled"])
        self.source_button.state(["disabled"] if self.busy else ["!disabled"])
        self.spd640_button.state(["disabled"] if self.busy else ["!disabled"])
        self.output_button.state(["disabled"] if self.busy else ["!disabled"])
        self.report_option.state(["disabled"] if self.busy else ["!disabled"])
        self.json_option.state(["disabled"] if self.busy else ["!disabled"])
        if self.busy:
            self.progress.grid()
        else:
            self.progress.grid_remove()

        self.validation_mode_label.configure(
            text=_validation_mode_text(has_spd640, self.require_spd640.get(), _control_report_kind(self.spd640_path.get()))
        )
        self.disabled_reason.set(self._disabled_reason(can_validate, can_generate))
        self._refresh_dashboard()
        self._refresh_status_badge()

    def _refresh_dashboard(self) -> None:
        if hasattr(self, "log_text"):
            _set_text(self.log_text, "\n".join(self.activity_log))

    def _refresh_status_badge(self) -> None:
        if self.busy:
            label, status, icon = "En cours", "warning", "warning"
        elif self.last_error:
            label, status, icon = "À corriger", "error", "error"
        elif self.last_result and self.last_result.conversion and self.last_result.conversion.output_path:
            label, status, icon = "MND créé", "success", "check"
        elif self.last_result:
            label, status, icon = "Validé", "success", "check"
        elif self.source_path.get().strip():
            label, status, icon = "À valider", "warning", "warning"
        else:
            label, status, icon = "Prêt", "success", "check"
        bg, fg = status_colors(status)
        self.status_badge.configure(text=label, icon=icon, background=bg, foreground=fg)
        success_bg, success_fg = status_colors("success")
        self.security_badge.configure(text="Sécurité", icon="shield", background=success_bg, foreground=success_fg)
        self._refresh_update_badge()

    def _refresh_update_badge(self) -> None:
        if not hasattr(self, "update_badge"):
            return
        if self.last_update_result and self.last_update_result.update_available:
            label, status, icon = "Mise à jour", "warning", "warning"
        elif self.last_update_result and self.last_update_result.ok:
            label, status, icon = "À jour", "success", "check"
        elif self.last_update_result and not self.last_update_result.ok:
            label, status, icon = "Version ?", "warning", "warning"
        else:
            label, status, icon = "Version ?", "warning", "warning"
        bg, fg = status_colors(status)
        self.update_badge.configure(text=label, icon=icon, background=bg, foreground=fg)

    def _set_initial_geometry(self) -> None:
        screen_width = max(1, self.winfo_screenwidth())
        screen_height = max(1, self.winfo_screenheight())
        width = max(1180, min(1360, int(screen_width * 0.9)))
        height = max(760, min(940, int(screen_height * 0.9)))
        x = max(0, int((screen_width - width) / 2))
        y = max(0, int((screen_height - height) / 2))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(1080, 720)

    def _can_validate(self) -> bool:
        if self.busy:
            return False
        source = build_file_preview(self.source_path.get(), label="EmployeurD", suffixes=(".txt",), optional=False)
        output = build_output_preview(
            self.source_path.get(),
            self.output_dir.get(),
            include_report=self.write_report_md.get(),
            include_validation_json=self.write_validation_json.get(),
        )
        return source.ok and output.ok

    def _can_generate(self) -> bool:
        return bool(self._can_validate() and self.last_result and self.last_result.ok)

    def _disabled_reason(self, can_validate: bool, can_generate: bool) -> str:
        if self.busy:
            return "Une opération locale est en cours."
        if not can_validate:
            if not self.source_path.get().strip():
                return "Ajoutez d'abord l'écriture EmployeurD."
            return "Corrigez les choix avant de vérifier."
        if not can_generate:
            return "Le MND sera disponible après une vérification réussie."
        return "Prêt à créer le fichier MND."

    def _set_update_check_on_startup(self, enabled: bool) -> None:
        try:
            remember_update_check_on_startup(enabled)
            self.preferences = load_preferences()
        except OSError:
            messagebox.showwarning("Préférences", "Impossible d'enregistrer cette préférence locale.")

    def _remember_output_dir(self, output_dir: str) -> None:
        try:
            remember_output_dir(output_dir)
            self.preferences = load_preferences()
        except OSError:
            pass

    def _resolved_output_root(self) -> Path:
        output = self.output_dir.get().strip()
        return Path(output) if output else default_output_root()

    def _log_event(self, message: str) -> None:
        self.activity_log.append(_timestamped(message))
        if hasattr(self, "log_text"):
            self._refresh_dashboard()


def _optional_path(value: str) -> Path | None:
    cleaned = value.strip()
    return Path(cleaned) if cleaned else None


def _usable_saved_output_dir(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    path = Path(cleaned)
    temp_root = Path(tempfile.gettempdir())
    try:
        if path.resolve().is_relative_to(temp_root.resolve()):
            return ""
    except OSError:
        return ""
    return cleaned


def _card(parent: ttk.Frame) -> tk.Frame:
    frame = tk.Frame(
        parent,
        background=Palette.surface,
        highlightbackground=Palette.border,
        highlightcolor=Palette.border,
        highlightthickness=1,
        bd=0,
        padx=14,
        pady=12,
    )
    frame.grid_columnconfigure(0, weight=1)
    return frame


def _card_title(parent: ttk.Frame, step: str, title: str, subtitle: str) -> ttk.Frame:
    frame = ttk.Frame(parent, style="CardBody.TFrame")
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text=step, style="StepBadge.TLabel").grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 10), pady=(1, 0))
    ttk.Label(frame, text=title, style="Title.TLabel").grid(row=0, column=1, sticky="w")
    ttk.Label(frame, text=subtitle, style="SmallMuted.TLabel", wraplength=500).grid(row=1, column=1, sticky="ew", pady=(1, 0))
    return frame


def _link_label(parent: tk.Widget, text: str, command) -> ttk.Label:
    label = ttk.Label(parent, text=text, style="Link.TLabel", cursor="hand2")
    label.bind("<Button-1>", lambda _event: command())
    return label


def _badge_label(parent: tk.Widget, text: str) -> StatusBadge:
    return StatusBadge(parent, text)


def _subpanel(parent: tk.Widget) -> tk.Frame:
    panel = tk.Frame(
        parent,
        background=Palette.surface_alt,
        highlightbackground=Palette.border,
        highlightcolor=Palette.border,
        highlightthickness=1,
        bd=0,
        padx=12,
        pady=9,
    )
    panel.columnconfigure(1, weight=1)
    return panel


def _panel_title(parent: tk.Widget, text: str) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        background=Palette.surface_alt,
        foreground=Palette.primary_dark,
        font=("Segoe UI Semibold", 9),
    )


def _dashboard_text(parent: tk.Widget, *, height: int, font_size: int = 10) -> tk.Text:
    return tk.Text(
        parent,
        height=height,
        wrap="word",
        borderwidth=0,
        relief="flat",
        highlightbackground=Palette.border,
        highlightcolor=Palette.border,
        highlightthickness=1,
        padx=14,
        pady=12,
        font=("Segoe UI", font_size),
        background=Palette.surface_alt,
        foreground=Palette.text,
        cursor="arrow",
    )

def _validation_mode_text(has_report: bool, strict: bool, report_kind: str) -> str:
    if strict:
        return f"{report_kind} est obligatoire. Si un contrôle échoue, le MND ne sera pas créé."
    if has_report and report_kind == "SPD640-P":
        return "Le SPD640-P sera comparé aux totaux débit/crédit de l'écriture avant la création du MND."
    if has_report and report_kind == "SPD681":
        return "Le SPD681 sera lu comme contrôle RRQ/AE/RQAP. Il ne remplace pas le SPD640-P pour les débits/crédits."
    if has_report:
        return "Le rapport fourni sera vérifié avant la création du MND."
    return "Le TXT sera vérifié seul. Ajoutez un SPD640-P pour confirmer les totaux de paie."


def _control_report_kind(value: str) -> str:
    path = Path(value.strip()) if value.strip() else None
    if not path:
        return "rapport de contrôle"
    name = path.name.lower()
    if "spd681" in name or path.suffix.lower() == ".xml":
        return "SPD681"
    if "spd640" in name or path.suffix.lower() == ".csv":
        return "SPD640-P"
    return "rapport de contrôle"


def _generated_outputs_message(result: GuiOperationResult) -> str:
    labels = _generated_output_labels(result, with_articles=True)
    verb = "a été généré" if len(labels) == 1 else "ont été générés"
    return f"{_capitalize(_join_french(labels))} {verb}."


def _generated_outputs_status(result: GuiOperationResult) -> str:
    labels = _generated_output_labels(result, with_articles=True)
    if len(labels) == 1:
        return f"{_capitalize(labels[0])} est prêt à être consulté."
    return "Les fichiers générés sont prêts à être consultés."


def _generated_outputs_log(result: GuiOperationResult) -> str:
    labels = _generated_output_labels(result, with_articles=False)
    return f"Généré : {_join_french(labels)}."


def _generated_output_labels(result: GuiOperationResult, *, with_articles: bool) -> tuple[str, ...]:
    conversion = result.conversion
    if not conversion:
        return ("les fichiers demandés",) if with_articles else ("fichiers demandés",)

    labels: list[str] = []
    if conversion.output_path:
        labels.append("le fichier MND" if with_articles else "MND")
    if conversion.report_path:
        labels.append("le rapport Markdown" if with_articles else "rapport Markdown")
    if conversion.validation_json_path:
        labels.append("le JSON de validation" if with_articles else "JSON de validation")
    if labels:
        return tuple(labels)
    return ("les fichiers demandés",) if with_articles else ("fichiers demandés",)


def _join_french(values: tuple[str, ...]) -> str:
    if len(values) <= 1:
        return values[0] if values else ""
    if len(values) == 2:
        return f"{values[0]} et {values[1]}"
    return f"{', '.join(values[:-1])} et {values[-1]}"


def _capitalize(value: str) -> str:
    return value[:1].upper() + value[1:] if value else value


def _output_files_text(files: tuple[str, ...]) -> str:
    if not files:
        return "Fichiers à créer : selon les options choisies."
    return "Fichiers à créer :\n" + "\n".join(f"- {name}" for name in files)


def _timestamped(message: str) -> str:
    return f"{datetime.now().strftime('%H:%M:%S')} - {message}"


def _file_preview_text(preview) -> str:
    if preview.status == "success":
        return ""
    if preview.path is None:
        return ""
    return f"{preview.title} : {preview.detail}"


def _set_optional_label(label: ttk.Label, text: str) -> None:
    label.configure(text=text)
    if text:
        label.grid()
    else:
        label.grid_remove()


def _set_text(widget: tk.Text, value: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.tag_configure("section", font=("Segoe UI Semibold", 10), foreground=Palette.primary_dark, spacing1=7, spacing3=3)
    widget.tag_configure("error", foreground=Palette.danger)
    sections = {"Résumé", "Contrôles", "Rapport et validation", "Journal"}
    for line in value.splitlines():
        normalized = line.lower()
        is_error = "à corriger" in normalized or ("erreur" in normalized and "aucune erreur" not in normalized)
        tag = "section" if line in sections else "error" if is_error else ""
        widget.insert("end", line + "\n", (tag,) if tag else ())
    widget.configure(state="disabled")


def main() -> int:
    app = EmployeurDMegaGestApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

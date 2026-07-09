from __future__ import annotations

import queue
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import load_app_config
from .errors import ConfigurationError, ConversionError, ValidationFailed
from .gui_controller import GuiController, GuiOperationResult
from .gui_dialogs import show_legal_notice, show_security_window, show_support_window
from .gui_state import (
    build_file_preview,
    build_output_preview,
    default_output_root,
    generated_files,
    summary_text,
)
from .gui_texts import (
    APP_DISPLAY_NAME,
    APP_SUBTITLE,
    COPYRIGHT_TEXT,
    REPOSITORY_LINK_TEXT,
    REPOSITORY_URL,
    SPONSOR_LINK_TEXT,
    SPONSOR_URL,
    Text,
    WEBSITE_LINK_TEXT,
    WEBSITE_URL,
)
from .gui_theme import Palette, configure_theme, status_colors
from .models import ConversionResult, ReconciliationResult
from .platform_actions import open_folder
from .preferences import ensure_preferences_dir, load_preferences, remember_output_dir
from .resource_paths import default_config_dir, package_asset_path
from .update_check import DEFAULT_TIMEOUT_SECONDS, DEFAULT_UPDATE_URL, UpdateCheckResult, check_for_update, configured_update_url
from .user_messages import friendly_error_message, technical_error_message
from .version import __version__


_STATUS_ICON_CACHE: dict[str, tk.PhotoImage] | None = None
UPDATE_CHECK_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_SECONDS
UPDATE_CHECK_UI_DEADLINE_SECONDS = 2.5
JOURNAL_LINK_PREFIX = "::link::"
SECURITY_TOOLTIP_TEXT = "\n".join(
    [
        "Traitement local des fichiers de paie.",
        "Aucun fichier de paie transmis.",
        "Logs conservés sur cet ordinateur.",
        "GitHub est consulté seulement pour les métadonnées publiques.",
        "SHA256 et rapports de sécurité vérifiables pour le ZIP officiel.",
    ]
)


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


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str, *, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None
        for target in _widget_tree(widget):
            target.bind("<Enter>", self._schedule, add="+")
            target.bind("<Leave>", self._hide, add="+")
            target.bind("<ButtonPress>", lambda event: self._hide(event, force=True), add="+")

    def _schedule(self, _event=None) -> None:  # noqa: ANN001
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _show(self) -> None:
        self._after_id = None
        if self._window or not self.text:
            return
        x = self.widget.winfo_pointerx() + 14
        y = self.widget.winfo_pointery() + 12
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{x}+{y}")
        window.configure(background=Palette.text)
        label = tk.Label(
            window,
            text=self.text,
            justify="left",
            wraplength=360,
            background=Palette.text,
            foreground="#ffffff",
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        )
        label.grid(row=0, column=0)
        self._window = window

    def _hide(self, _event=None, *, force: bool = False) -> None:  # noqa: ANN001
        if not force and self._pointer_inside_widget():
            return
        self._cancel()
        if self._window:
            self._window.destroy()
            self._window = None

    def _cancel(self) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _pointer_inside_widget(self) -> bool:
        x = self.widget.winfo_pointerx()
        y = self.widget.winfo_pointery()
        left = self.widget.winfo_rootx()
        top = self.widget.winfo_rooty()
        return left <= x <= left + self.widget.winfo_width() and top <= y <= top + self.widget.winfo_height()


def _widget_tree(widget: tk.Widget) -> tuple[tk.Widget, ...]:
    widgets = [widget]
    for child in widget.winfo_children():
        widgets.extend(_widget_tree(child))
    return tuple(widgets)


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
            padx=9,
            pady=6,
            cursor="hand2",
        )
        self.variable = variable
        self.command = command
        self._disabled = False
        self._locked = False
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
            wraplength=240,
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
        if "locked" in states:
            self._locked = True
        if "!locked" in states:
            self._locked = False
        self._redraw()
        current_state = []
        if self._disabled:
            current_state.append("disabled")
        if self._locked:
            current_state.append("locked")
        return tuple(current_state)

    def _toggle(self, _event=None) -> None:
        if self._disabled or self._locked:
            return
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def _redraw(self) -> None:
        checked = self.variable.get()
        locked_checked = self._locked and checked and not self._disabled
        bg = Palette.disabled_bg if self._disabled else Palette.success_bg if locked_checked else Palette.info_bg if checked else Palette.surface
        border = Palette.disabled_bg if self._disabled else Palette.success if locked_checked else Palette.primary if checked else Palette.border
        fg = Palette.disabled if self._disabled else Palette.text
        muted = Palette.disabled if self._disabled else Palette.muted
        cursor = "arrow" if self._disabled or self._locked else "hand2"

        self.configure(background=bg, highlightbackground=border, cursor=cursor)
        self._box.configure(background=bg, cursor=cursor)
        self._title.configure(background=bg, foreground=fg, cursor=cursor)
        self._description.configure(background=bg, foreground=muted, cursor=cursor)

        self._box.delete("all")
        outline = Palette.disabled if self._disabled else Palette.success if locked_checked else Palette.primary if checked else Palette.border_strong
        fill = Palette.success if locked_checked else Palette.primary if checked and not self._disabled else Palette.surface
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
        self._update_scrollregion()

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._update_scrollregion()

    def _update_scrollregion(self) -> None:
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        canvas_height = max(1, self.canvas.winfo_height())
        content_height = max(1, bbox[3] - bbox[1])
        if content_height <= canvas_height + 24:
            self.canvas.yview_moveto(0)
            self.canvas.configure(scrollregion=(bbox[0], bbox[1], bbox[2], canvas_height))
            return
        self.canvas.configure(scrollregion=bbox)

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

        self.app_config = load_app_config(default_config_dir())
        self.controller = GuiController(config_dir=default_config_dir())
        try:
            ensure_preferences_dir()
        except OSError:
            pass
        self.preferences = load_preferences(
            default_update_check_on_startup=self.app_config.updates.get("check_on_startup") is True
        )
        self.source_path = tk.StringVar()
        self.spd640_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=_usable_saved_output_dir(self.preferences.output_dir))
        self.require_spd640 = tk.BooleanVar(value=False)
        self.write_report_md = tk.BooleanVar(value=False)
        self.write_validation_json = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Prêt à commencer")
        self.status_detail = tk.StringVar(value="Ajoutez l'écriture EmployeurD. Sans dossier choisi, la sortie ira dans Documents.")
        self.disabled_reason = tk.StringVar(value="")
        self.last_result: GuiOperationResult | None = None
        self.last_error: Exception | None = None
        self.last_update_result: UpdateCheckResult | None = None
        self.update_check_running = False
        self.busy = False
        self.activity_log: list[str] = [_timestamped("Ouverture de l'application. Ajoutez l'écriture EmployeurD pour commencer.")]
        self.journal_summaries: list[tuple[str, str]] = []
        self._task_queue: queue.Queue[tuple[bool, object]] = queue.Queue()
        self._task_on_success = None

        configure_theme(self)
        self._build_ui()
        self._bind_shortcuts()
        self._refresh_all()

        if self.preferences.update_check_on_startup:
            self.after(750, lambda: self._check_update(silent=True))

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
        self.scroll_area = ScrollableFrame(self, padding=(14, 8, 14, 2))
        self.scroll_area.grid(row=1, column=0, sticky="nsew")
        body = self.scroll_area.content
        body.columnconfigure(0, weight=7)
        body.columnconfigure(1, weight=5)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)
        self._build_inputs_card(left).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._build_validation_card(left).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self._build_output_card(left).grid(row=2, column=0, sticky="ew")

        right = ttk.Frame(body, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self._build_dashboard_card(right).grid(row=0, column=0, sticky="nsew")

        self._build_action_bar().grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))
        self._build_footer().grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))

        for variable in (self.source_path, self.spd640_path):
            variable.trace_add("write", lambda *_: self._mark_dirty())
        self.output_dir.trace_add("write", lambda *_: self._refresh_all())

    def _build_header(self) -> ttk.Frame:
        header = ttk.Frame(self, style="Header.TFrame", padding=(16, 9))
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
        self.status_badge = _badge_label(badges, "Paie à préparer")
        self.security_badge = _badge_label(badges, "Sécurité OK")
        self.update_badge = _badge_label(badges, "Version non vérifiée")
        self.status_badge.grid(row=0, column=0, padx=(0, 8))
        self.security_badge.grid(row=0, column=1, padx=(0, 8))
        self.update_badge.grid(row=0, column=2)
        self._security_tooltip = Tooltip(self.security_badge, SECURITY_TOOLTIP_TEXT)
        return header

    def _build_inputs_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = _card(parent)
        _card_title(card, "1", "Fichiers EmployeurD", "Ajoutez le TXT de paie. Le PDF GL peut confirmer les montants.").grid(row=0, column=0, columnspan=3, sticky="ew")
        card.columnconfigure(1, weight=1)

        _file_heading(card, "Écriture détaillée EmployeurD (TXT)", "OBLIGATOIRE", "RequiredBadge.TLabel").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        ttk.Label(
            card,
            text="À fournir pour créer le fichier MND.",
            style="SmallMuted.TLabel",
            wraplength=430,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 1))
        ttk.Entry(card, textvariable=self.source_path).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self.source_button = ttk.Button(card, text=Text.choose, command=self._choose_source, style="Action.TButton")
        self.source_button.grid(row=3, column=2, sticky="e", padx=(10, 0), pady=(3, 0))
        self.source_meta = ttk.Label(card, text="", style="SmallMuted.TLabel", wraplength=430, justify="left")
        self.source_meta.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        ttk.Separator(card).grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)
        _file_heading(card, "Grand détail de l'écriture GL (PDF)", "FACULTATIF", "OptionalBadge.TLabel").grid(row=6, column=0, columnspan=3, sticky="ew")
        ttk.Label(
            card,
            text="Utilisez le PDF original généré par EmployeurD, non scanné ni modifié.",
            style="SmallMuted.TLabel",
            wraplength=430,
            justify="left",
        ).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(1, 1))
        ttk.Entry(card, textvariable=self.spd640_path).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        spd_actions = ttk.Frame(card, style="CardBody.TFrame")
        spd_actions.grid(row=8, column=2, sticky="e", padx=(10, 0), pady=(3, 0))
        self.spd640_button = ttk.Button(spd_actions, text=Text.choose, command=self._choose_spd640, style="Action.TButton")
        self.spd640_button.grid(row=0, column=0, padx=(0, 6))
        self.clear_spd640_button = ttk.Button(spd_actions, text=Text.remove, command=self._clear_spd640, style="Quiet.TButton")
        self.clear_spd640_button.grid(row=0, column=1)
        self.spd640_meta = ttk.Label(card, text="", style="SmallMuted.TLabel", wraplength=430, justify="left")
        self.spd640_meta.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        return card

    def _build_validation_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = _card(parent)
        _card_title(card, "2", "Concordance", "Avec le PDF GL, la création bloque si les montants ne concordent pas.").grid(row=0, column=0, sticky="ew")
        self.validation_mode_label = ttk.Label(card, text="", style="HintInfo.TLabel", wraplength=430, justify="left")
        self.validation_mode_label.grid(row=1, column=0, sticky="ew", pady=(5, 4))
        self.require_spd640_check = CheckOption(
            card,
            variable=self.require_spd640,
            command=self._mark_dirty,
            text="Concordance du rapport obligatoire",
            description="S'active automatiquement dès qu'un rapport est ajouté.",
        )
        self.require_spd640_check.grid(row=2, column=0, sticky="ew", pady=(2, 0))
        return card

    def _build_output_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = _card(parent)
        _card_title(card, "3", "Destination", "Choisissez le dossier parent. L'application créera le sous-dossier horodaté.").grid(row=0, column=0, columnspan=3, sticky="ew")
        card.columnconfigure(0, weight=1)
        ttk.Entry(card, textvariable=self.output_dir).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.output_button = ttk.Button(card, text=Text.choose, command=self._choose_output_dir, style="Action.TButton")
        self.output_button.grid(row=1, column=2, sticky="e", padx=(10, 0), pady=(6, 0))
        self.output_meta = ttk.Label(card, text="", style="SmallMuted.TLabel", wraplength=430, justify="left")
        self.output_meta.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.output_files = ttk.Label(card, text="", style="SmallMuted.TLabel", wraplength=430, justify="left")
        self.output_files.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        options = ttk.Frame(card, style="CardBody.TFrame")
        options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))
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
        self.log_text = _dashboard_text(journal_panel, height=13, font_size=9)
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
            padx=12,
            pady=8,
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
        self.folder_button = ttk.Button(secondary, text=Text.open_folder, command=self._open_folder, style="Action.TButton")
        self.folder_button.grid(row=0, column=0)
        return bar

    def _build_footer(self) -> ttk.Frame:
        footer = ttk.Frame(self, style="App.TFrame")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text=COPYRIGHT_TEXT, style="Footer.TLabel").grid(row=0, column=0, sticky="w")
        links = ttk.Frame(footer, style="App.TFrame")
        links.grid(row=0, column=1, sticky="e")
        _link_label(links, Text.legal, lambda: show_legal_notice(self)).grid(row=0, column=0, padx=(0, 12))
        _link_label(links, WEBSITE_LINK_TEXT, lambda: webbrowser.open(WEBSITE_URL)).grid(row=0, column=1, padx=(0, 12))
        _link_label(links, REPOSITORY_LINK_TEXT, lambda: webbrowser.open(REPOSITORY_URL)).grid(row=0, column=2, padx=(0, 12))
        ttk.Button(links, text=SPONSOR_LINK_TEXT, command=lambda: webbrowser.open(SPONSOR_URL), style="Sponsor.TButton").grid(row=0, column=3, padx=(0, 12))
        _link_label(links, Text.security, self._show_security).grid(row=0, column=4, padx=(0, 12))
        _link_label(links, Text.support, self._show_support).grid(row=0, column=5, padx=(0, 12))
        self.update_button = ttk.Button(links, text=Text.check_updates, command=lambda: self._check_update(silent=False), style="Quiet.TButton")
        self.update_button.grid(row=0, column=6)
        return footer

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-o>", lambda _event: self._choose_source())
        self.bind_all("<Control-O>", lambda _event: self._choose_source())
        self.bind_all("<Control-g>", lambda _event: self._generate())
        self.bind_all("<Control-G>", lambda _event: self._generate())
        self.bind_all("<F5>", lambda _event: self._check_update(silent=False))

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
            title="Choisir le rapport de contrôle",
            filetypes=[
                ("Rapports GL PDF", "*.pdf *.PDF"),
                ("Rapports SPD640-P", "*.csv *.CSV"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if selected:
            self.spd640_path.set(selected)
            self.require_spd640.set(_control_report_kind(selected) in {"Grand détail GL", "SPD640-P"})
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
        require_spd640 = bool(spd640_path)
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
        require_spd640 = bool(spd640_path)
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
        self._append_journal_summary("Résumé de la vérification", result, include_outputs=False)

    def _generation_succeeded(self, result: GuiOperationResult) -> None:
        self._remember_output_dir(self.output_dir.get())
        self.last_result = result
        self.status.set("MND créé")
        self.status_detail.set(_generated_outputs_status(result))
        self._log_event(_generated_outputs_log(result))
        self._append_journal_summary("Résumé de la génération", result, include_outputs=True)
        messagebox.showinfo("Conversion terminée", _generated_outputs_message(result))

    def _show_error(self, error: Exception) -> None:
        self.last_result = None
        self.last_error = error
        self._clear_payroll_summaries()
        self.status.set("À corriger")
        self.status_detail.set("Aucun MND ne sera créé tant que le problème n'est pas réglé.")
        self._log_event("Problème à corriger. Création du MND désactivée.")
        messagebox.showerror(
            "À corriger avant de créer le MND",
            f"{friendly_error_message(error)}\n\nDétails à transmettre au support:\n{technical_error_message(error)}",
        )

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
        show_security_window(
            self,
            update_url=str(self.app_config.updates.get("url", "")),
        )

    def _show_support(self) -> None:
        show_support_window(self)

    def _check_update(self, *, silent: bool) -> None:
        if self.busy or self.update_check_running:
            if not silent and self.busy:
                self._log_event("Vérification de version reportée: une opération locale est en cours.")
            return
        config = load_app_config(default_config_dir())
        update_url = str(config.updates.get("url", ""))
        resolved_url = configured_update_url(update_url)
        if silent and resolved_url != DEFAULT_UPDATE_URL:
            self._log_event("Vérification automatique ignorée: canal de mise à jour personnalisé.")
            self.last_update_result = None
            self._refresh_update_badge()
            return
        deadline = time.monotonic() + UPDATE_CHECK_UI_DEADLINE_SECONDS
        self.update_check_running = True
        self._log_event("Vérification de version en arrière-plan." if silent else "Vérification manuelle de la version en cours.")
        if not silent:
            self.update_button.configure(text="Vérification...")
            self.update_button.state(["disabled"])
        self._refresh_update_badge()
        result_queue: queue.Queue[UpdateCheckResult] = queue.Queue()

        def worker() -> None:
            try:
                result_queue.put(check_for_update(update_url, timeout=UPDATE_CHECK_TIMEOUT_SECONDS))
            except Exception as error:
                result_queue.put(_unexpected_update_check_failure(resolved_url, error))

        def poll() -> None:
            try:
                result = result_queue.get_nowait()
            except queue.Empty:
                if time.monotonic() >= deadline:
                    if self.winfo_exists():
                        self.update_check_running = False
                        if not silent:
                            self.update_button.state(["!disabled"])
                        self._update_check_finished(_update_check_deadline_failure(resolved_url), silent=silent)
                    return
                if self.winfo_exists():
                    self.after(100, poll)
                return
            if self.winfo_exists():
                self.update_check_running = False
                if not silent:
                    self.update_button.state(["!disabled"])
                self._update_check_finished(result, silent=silent)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _update_check_finished(self, result: UpdateCheckResult, *, silent: bool) -> None:
        self.last_update_result = result
        if result.update_available:
            self.status.set("Mise à jour disponible")
            self.status_detail.set("Une nouvelle version est disponible. Rien ne sera installé automatiquement.")
            latest = f" {result.latest_version}" if result.latest_version else ""
            self._log_event(f"Mise à jour disponible{latest}.")
        elif result.ok:
            self._log_event("Version vérifiée: application à jour.")
        else:
            self._log_event("Vérification de version reportée. L'application demeure utilisable.")
        if not silent:
            self.update_button.configure(text=Text.check_updates)
        self._append_update_summary(result)
        self._refresh_update_badge()

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
        self._clear_payroll_summaries()
        self.status.set("Vérification à refaire")
        self.status_detail.set("Les choix ont changé. Vérifiez de nouveau avant de créer le MND.")
        self._refresh_all()

    def _refresh_all(self) -> None:
        source_preview = build_file_preview(self.source_path.get(), label="EmployeurD", suffixes=(".txt",), optional=False)
        spd_preview = build_file_preview(
            self.spd640_path.get(),
            label="Rapport de contrôle",
            suffixes=(".pdf", ".csv"),
            optional=True,
        )
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
        if has_spd640 and not self.require_spd640.get():
            self.require_spd640.set(True)
        elif not has_spd640 and self.require_spd640.get():
            self.require_spd640.set(False)
        if self.busy:
            self.require_spd640_check.state(["disabled", "!locked"])
        elif has_spd640:
            self.require_spd640_check.state(["!disabled", "locked"])
        else:
            self.require_spd640_check.state(["disabled", "!locked"])
        self.clear_spd640_button.state(["!disabled"] if has_spd640 and not self.busy else ["disabled"])

        can_validate = self._can_validate()
        can_generate = self._can_generate()
        self.validate_button.state(["!disabled"] if can_validate else ["disabled"])
        self.generate_button.state(["!disabled"] if can_generate else ["disabled"])
        self.validate_button.configure(style="Action.TButton" if can_generate else "Primary.TButton")
        self.generate_button.configure(style="Primary.TButton" if can_generate else "Action.TButton")
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
            text=_validation_mode_text(has_spd640, self.require_spd640.get(), _control_report_kind(self.spd640_path.get())),
            style=_validation_mode_style(has_spd640, self.require_spd640.get()),
        )
        self.disabled_reason.set(self._disabled_reason(can_validate, can_generate))
        self._refresh_dashboard()
        self._refresh_status_badge()

    def _refresh_dashboard(self) -> None:
        if hasattr(self, "log_text"):
            _set_journal_text(self.log_text, self.activity_log, self.journal_summaries)

    def _refresh_status_badge(self) -> None:
        if self.busy:
            label, status, icon = "Paie en cours", "warning", "warning"
        elif self.last_error:
            label, status, icon = "Paie à corriger", "error", "error"
        elif self.last_result and self.last_result.conversion and self.last_result.conversion.output_path:
            label, status, icon = "MND créé", "success", "check"
        elif self.last_result:
            label, status, icon = "Paie validée", "success", "check"
        elif self.source_path.get().strip():
            label, status, icon = "Paie à vérifier", "warning", "warning"
        else:
            label, status, icon = "Paie à préparer", "info", "dot"
        bg, fg = status_colors(status)
        self.status_badge.configure(text=label, icon=icon, background=bg, foreground=fg)
        success_bg, success_fg = status_colors("success")
        self.security_badge.configure(text="Sécurité OK", icon="shield", background=success_bg, foreground=success_fg)
        self._refresh_update_badge()

    def _refresh_update_badge(self) -> None:
        if not hasattr(self, "update_badge"):
            return
        if self.update_check_running:
            label, status, icon = "Vérification en cours", "info", "dot"
        elif self.last_update_result and self.last_update_result.update_available:
            label, status, icon = "Mise à jour disponible", "warning", "warning"
        elif self.last_update_result and self.last_update_result.ok:
            label, status, icon = "Version à jour", "success", "check"
        elif self.last_update_result and not self.last_update_result.ok:
            label, status, icon = "Vérification reportée", "warning", "warning"
        else:
            label, status, icon = "Version non vérifiée", "info", "dot"
        bg, fg = status_colors(status)
        self.update_badge.configure(text=label, icon=icon, background=bg, foreground=fg)

    def _set_initial_geometry(self) -> None:
        screen_width = max(1, self.winfo_screenwidth())
        screen_height = max(1, self.winfo_screenheight())
        horizontal_margin = 48 if screen_width >= 1280 else 24
        vertical_margin = 64 if screen_height >= 900 else 50
        width = min(1360, max(1040, screen_width - horizontal_margin))
        height = min(960, max(680, screen_height - vertical_margin))
        width = min(width, screen_width)
        height = min(height, screen_height)
        x = max(0, int((screen_width - width) / 2))
        y = max(0, int((screen_height - height) / 2))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(1040, width), min(660, height))

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

    def _append_journal_summary(self, title: str, result: GuiOperationResult, *, include_outputs: bool) -> None:
        if not result.conversion:
            return
        summary_kind = "generation" if include_outputs else "validation"
        output_files = generated_files(result.conversion) if include_outputs else ()
        self.journal_summaries.append(
            (
                summary_kind,
                _journal_summary_block(
                    title,
                    result.conversion,
                    result.reconciliations,
                    output_files=output_files,
                    include_mnd_recheck=include_outputs,
                ),
            )
        )
        if hasattr(self, "log_text"):
            self._refresh_dashboard()

    def _append_update_summary(self, result: UpdateCheckResult) -> None:
        self.journal_summaries = [summary for summary in self.journal_summaries if summary[0] not in {"update", "update_available"}]
        kind = "update_available" if result.update_available else "update"
        self.journal_summaries.append((kind, _journal_update_block(result)))
        if hasattr(self, "log_text"):
            self._refresh_dashboard()

    def _clear_payroll_summaries(self) -> None:
        self.journal_summaries = [summary for summary in self.journal_summaries if summary[0] in {"update", "update_available"}]


def _optional_path(value: str) -> Path | None:
    cleaned = value.strip()
    return Path(cleaned) if cleaned else None


def _unexpected_update_check_failure(url: str, error: Exception) -> UpdateCheckResult:
    return UpdateCheckResult(
        ok=False,
        update_available=False,
        current_version=__version__,
        latest_version=None,
        url=url,
        message=f"Vérification impossible pour le moment: erreur interne ({error.__class__.__name__}).",
    )


def _update_check_deadline_failure(url: str) -> UpdateCheckResult:
    return UpdateCheckResult(
        ok=False,
        update_available=False,
        current_version=__version__,
        latest_version=None,
        url=url,
        message="Vérification reportée: le réseau répond trop lentement.",
    )


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
        pady=8,
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


def _file_heading(parent: ttk.Frame, title: str, badge: str, badge_style: str) -> ttk.Frame:
    frame = ttk.Frame(parent, style="CardBody.TFrame")
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, text=title, style="Title.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(frame, text=badge, style=badge_style).grid(row=0, column=1, sticky="e", padx=(10, 0))
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
        pady=7,
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
        padx=12,
        pady=9,
        font=("Segoe UI", font_size),
        background=Palette.surface_alt,
        foreground=Palette.text,
        cursor="arrow",
    )

def _validation_mode_text(has_report: bool, strict: bool, report_kind: str) -> str:
    if has_report and report_kind == "Grand détail GL":
        return "Le PDF GL original est actif : ses totaux et ses comptes doivent concorder avec l'écriture."
    if has_report and report_kind == "SPD640-P":
        return "Le SPD640-P est actif : ses totaux doivent concorder avec l'écriture, sinon le MND ne sera pas créé."
    if has_report:
        return "Le rapport fourni doit être un PDF GL ou un SPD640-P CSV."
    return "On vérifie l'écriture EmployeurD seule. Ajoutez le PDF GL original pour confirmer les montants."


def _validation_mode_style(has_report: bool, strict: bool) -> str:
    if has_report:
        return "HintSuccess.TLabel"
    return "HintInfo.TLabel"


def _control_report_kind(value: str) -> str:
    path = Path(value.strip()) if value.strip() else None
    if not path:
        return "rapport GL"
    name = path.name.lower()
    if path.suffix.lower() == ".pdf" or "détail des imputations comptables" in name or "detail des imputations comptables" in name:
        return "Grand détail GL"
    if "spd640" in name or path.suffix.lower() == ".csv":
        return "SPD640-P"
    return "rapport GL"


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
    labels = []
    for name in files:
        suffix = Path(name).suffix.lower()
        if suffix == ".mnd":
            labels.append("MND")
        elif suffix == ".md":
            labels.append("rapport Markdown")
        elif suffix == ".json":
            labels.append("validation JSON")
        else:
            labels.append(name)
    return f"Fichiers à créer : {_join_french(tuple(labels))}."


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


def _journal_summary_block(
    title: str,
    result: ConversionResult,
    reconciliations: list[ReconciliationResult],
    *,
    output_files: tuple[Path, ...] = (),
    include_mnd_recheck: bool = True,
) -> str:
    lines = [
        f"======= {title} =======",
        summary_text(result, reconciliations, include_mnd_recheck=include_mnd_recheck),
    ]
    if output_files:
        lines.extend(["", "Fichiers créés:"])
        lines.extend(f"- {path.name}" for path in output_files)
    return "\n".join(lines).strip()


def _journal_update_block(result: UpdateCheckResult) -> str:
    lines = ["======= Mise à jour ======="]
    if result.update_available:
        version = result.latest_version or "plus récente"
        lines.extend(
            [
                f"État: Nouvelle version disponible ({version}).",
                f"Version installée: {result.current_version}",
            ]
        )
        release_url = result.release_page_url or result.download_url
        if release_url:
            lines.append(_journal_link_line("Ouvrir la page de mise à jour", release_url))
    elif result.ok:
        lines.append(f"État: Application à jour ({result.current_version}).")
    else:
        lines.append("État: Vérification reportée. L'application demeure utilisable hors ligne.")
        if result.message:
            lines.append(f"Détail: {result.message}")
    lines.extend(["", "Aucun fichier de paie n'a été transmis."])
    return "\n".join(lines).strip()


def _journal_link_line(label: str, url: str) -> str:
    return f"{JOURNAL_LINK_PREFIX}{label}::{url}"


def _parse_journal_link(line: str) -> tuple[str, str] | None:
    if not line.startswith(JOURNAL_LINK_PREFIX):
        return None
    content = line.removeprefix(JOURNAL_LINK_PREFIX)
    if "::" not in content:
        return None
    label, url = content.split("::", 1)
    if not label or not url.startswith(("http://", "https://")):
        return None
    return label, url


def _set_journal_text(widget: tk.Text, activity_log: list[str], summaries: list[tuple[str, str]]) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.tag_configure("journal", foreground=Palette.text)
    widget.tag_configure("summary_header_validation", background=Palette.success_bg, foreground=Palette.success, font=("Segoe UI Semibold", 9), spacing1=7, spacing3=4)
    widget.tag_configure("summary_header_generation", background=Palette.info_bg, foreground=Palette.primary_dark, font=("Segoe UI Semibold", 9), spacing1=7, spacing3=4)
    widget.tag_configure("summary_header_update", background=Palette.disabled_bg, foreground=Palette.muted, font=("Segoe UI Semibold", 9), spacing1=7, spacing3=4)
    widget.tag_configure("summary_header_update_available", background=Palette.warning_bg, foreground=Palette.warning, font=("Segoe UI Semibold", 9), spacing1=7, spacing3=4)
    widget.tag_configure("summary_body", foreground=Palette.text, lmargin1=8, lmargin2=8)
    widget.tag_configure("summary_body_update_available", foreground=Palette.warning, font=("Segoe UI Semibold", 9), lmargin1=8, lmargin2=8)
    widget.tag_configure("summary_file", foreground=Palette.primary_dark, lmargin1=16, lmargin2=16)
    widget.tag_configure("summary_label", foreground=Palette.primary_dark, font=("Segoe UI Semibold", 9), lmargin1=8, lmargin2=8, spacing1=3)
    widget.tag_configure("summary_link", foreground=Palette.primary, underline=True, font=("Segoe UI Semibold", 9), lmargin1=8, lmargin2=8)
    widget.tag_bind("summary_link", "<Enter>", lambda _event: widget.configure(cursor="hand2"))
    widget.tag_bind("summary_link", "<Leave>", lambda _event: widget.configure(cursor=""))

    if activity_log:
        widget.insert("end", "\n".join(activity_log), ("journal",))

    link_index = 0
    for kind, block in summaries:
        if widget.index("end-1c") != "1.0":
            widget.insert("end", "\n\n")
        for line in block.splitlines():
            parsed_link = _parse_journal_link(line)
            if parsed_link:
                label, url = parsed_link
                link_tag = f"summary_link_{link_index}"
                link_index += 1
                widget.tag_configure(link_tag, foreground=Palette.primary, underline=True, font=("Segoe UI Semibold", 9), lmargin1=8, lmargin2=8)
                widget.tag_bind(link_tag, "<Enter>", lambda _event: widget.configure(cursor="hand2"))
                widget.tag_bind(link_tag, "<Leave>", lambda _event: widget.configure(cursor=""))
                widget.tag_bind(link_tag, "<Button-1>", lambda _event, target=url: webbrowser.open(target))
                widget.insert("end", f"{label}\n", ("summary_link", link_tag))
                continue
            if line.startswith("======="):
                if kind == "generation":
                    tag = "summary_header_generation"
                elif kind == "update_available":
                    tag = "summary_header_update_available"
                elif kind == "update":
                    tag = "summary_header_update"
                else:
                    tag = "summary_header_validation"
            elif line == "Fichiers créés:":
                tag = "summary_label"
            elif line.startswith("- "):
                tag = "summary_file"
            elif kind == "update_available" and line.startswith("État:"):
                tag = "summary_body_update_available"
            else:
                tag = "summary_body"
            widget.insert("end", f"{line}\n", (tag,))

    widget.see("end")
    widget.configure(state="disabled")


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

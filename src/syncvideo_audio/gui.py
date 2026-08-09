"""Professional Tk desktop UI for MP4 and editable CapCut hand-offs."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .capcut_registry import CapCutRegistry
from .manifest import CanvasSpec, seconds_to_us
from .pipeline import OutputMode, PipelineOutputs, export_timeline
from .planner import (
    AlignmentMode,
    PlannerConfig,
    build_timeline,
    inspect_media_numbering,
    sort_media,
)
from .runtime import configure_runtime_storage, resolve_executable, resource_path
from .transcription import WhisperConfig


COLORS = {
    "background": "#0B0D12",
    "surface": "#12151D",
    "surface_raised": "#181C26",
    "surface_hover": "#202634",
    "border": "#272D3A",
    "text": "#F5F7FB",
    "muted": "#9098A8",
    "subtle": "#626B7C",
    "accent": "#23D7C4",
    "accent_hover": "#45E5D4",
    "accent_text": "#06211E",
    "success": "#65D68A",
    "warning": "#FFB86B",
    "danger": "#FF6B7A",
}

CANVAS_PRESETS = {
    "Dọc 9:16  ·  1080 × 1920": CanvasSpec(1080, 1920, 30),
    "Ngang 16:9  ·  1920 × 1080": CanvasSpec(1920, 1080, 30),
    "Vuông 1:1  ·  1080 × 1080": CanvasSpec(1080, 1080, 30),
}

MEDIA_TYPE_LABELS = {
    ".jpg": "ẢNH",
    ".jpeg": "ẢNH",
    ".png": "ẢNH",
    ".webp": "ẢNH",
    ".bmp": "ẢNH",
    ".gif": "ẢNH",
}

ALIGNMENT_OPTIONS = {
    "Chia đều theo audio": AlignmentMode.EQUAL,
    "Căn chuẩn theo transcript": AlignmentMode.TRANSCRIPT,
}


class SyncVideoAudioApp(ttk.Frame):
    """Main desktop application; rendering work stays off the UI thread."""

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self._configure_theme()
        super().__init__(master, style="App.TFrame", padding=(28, 16, 28, 14))
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.media_paths: list[Path] = []
        self._build_variables()
        self._build_ui()
        self._detect_runtime()
        self.after(100, self._poll_events)

    def _configure_theme(self) -> None:
        self.master.configure(background=COLORS["background"])
        self.master.option_add("*Font", "{Segoe UI} 10")
        self.master.option_add("*TCombobox*Listbox.background", COLORS["surface_raised"])
        self.master.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.master.option_add("*TCombobox*Listbox.selectBackground", COLORS["accent"])
        self.master.option_add("*TCombobox*Listbox.selectForeground", COLORS["accent_text"])

        style = ttk.Style(self.master)
        style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["background"])
        style.configure("Header.TFrame", background=COLORS["background"])
        style.configure(
            "Card.TFrame",
            background=COLORS["surface"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            borderwidth=1,
            relief="solid",
        )
        style.configure("CardInner.TFrame", background=COLORS["surface"])
        style.configure("Toolbar.TFrame", background=COLORS["surface"])

        style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"])
        style.configure(
            "Title.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "Subtitle.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "CardTitle.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "CardMuted.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "CardWarning.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["warning"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "Field.TLabel",
            background=COLORS["surface"],
            foreground="#C8CEDA",
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "Status.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Badge.TLabel",
            background="#153A36",
            foreground=COLORS["accent"],
            padding=(12, 7),
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "WarningBadge.TLabel",
            background="#35291E",
            foreground=COLORS["warning"],
            padding=(12, 7),
            font=("Segoe UI Semibold", 9),
        )

        style.configure(
            "TEntry",
            fieldbackground=COLORS["surface_raised"],
            foreground=COLORS["text"],
            insertcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=(10, 6),
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", COLORS["accent"])],
            lightcolor=[("focus", COLORS["accent"])],
            darkcolor=[("focus", COLORS["accent"])],
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["surface_raised"],
            background=COLORS["surface_raised"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["muted"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=(9, 6),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["surface_raised"])],
            foreground=[("readonly", COLORS["text"])],
            bordercolor=[("focus", COLORS["accent"])],
        )

        style.configure(
            "Secondary.TButton",
            background=COLORS["surface_raised"],
            foreground="#DDE2EC",
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=(12, 6),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", COLORS["surface_hover"]), ("pressed", "#293141")],
            foreground=[("disabled", COLORS["subtle"])],
        )
        style.configure(
            "Ghost.TButton",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            borderwidth=0,
            padding=(10, 7),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", COLORS["surface_hover"])],
            foreground=[("active", COLORS["text"])],
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground=COLORS["accent_text"],
            bordercolor=COLORS["accent"],
            lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent"],
            padding=(22, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLORS["accent_hover"]), ("disabled", "#345D59")],
            foreground=[("disabled", "#A6B7B4")],
        )

        style.configure(
            "Dark.TCheckbutton",
            background=COLORS["surface"],
            foreground="#C8CEDA",
            indicatorbackground=COLORS["surface_raised"],
            indicatorforeground=COLORS["accent"],
            bordercolor=COLORS["border"],
            font=("Segoe UI", 9),
        )
        style.map(
            "Dark.TCheckbutton",
            background=[("active", COLORS["surface"])],
            foreground=[("active", COLORS["text"])],
            indicatorbackground=[("selected", COLORS["accent"])],
        )
        style.configure(
            "Treeview",
            background=COLORS["surface_raised"],
            fieldbackground=COLORS["surface_raised"],
            foreground="#DDE2EC",
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            rowheight=30,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            bordercolor=COLORS["border"],
            relief="flat",
            padding=(8, 8),
            font=("Segoe UI Semibold", 8),
        )
        style.map(
            "Treeview",
            background=[("selected", "#1D5B55")],
            foreground=[("selected", COLORS["text"])],
        )
        style.map("Treeview.Heading", background=[("active", COLORS["surface_hover"])])
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=COLORS["surface_raised"],
            background=COLORS["accent"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent"],
            thickness=5,
        )
        style.configure("Dark.TSeparator", background=COLORS["border"])

    def _build_variables(self) -> None:
        self.name_var = tk.StringVar(value="Video mới")
        self.audio_var = tk.StringVar()
        self.media_dir_var = tk.StringVar()
        self.transcript_var = tk.StringVar()
        self.alignment_var = tk.StringVar(value=next(iter(ALIGNMENT_OPTIONS)))
        self.output_var = tk.StringVar(value=str((Path.cwd() / "output").resolve()))
        self.draft_root_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=OutputMode.BOTH.value)
        self.canvas_var = tk.StringVar(value=next(iter(CANVAS_PRESETS)))
        self.image_duration_var = tk.StringVar(value="6")
        self.motion_var = tk.BooleanVar(value=True)
        self.burn_caption_var = tk.BooleanVar(value=True)
        self.register_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Sẵn sàng để tạo project")
        self.media_count_var = tk.StringVar(value="Chưa có media")
        self.media_warning_var = tk.StringVar()
        self.runtime_var = tk.StringVar(value="Đang kiểm tra CapCut…")

    def _build_ui(self) -> None:
        self.master.title("SyncVideo-Audio · CapCut Hand-off Studio")
        try:
            self.master.iconbitmap(default=str(resource_path("assets/logo.ico")))
        except (OSError, tk.TclError):
            pass
        try:
            # Tk uses the PNG fallback reliably even when a Windows build has
            # trouble decoding an ICO entry. Keep a reference for the lifetime
            # of the root window so the taskbar icon is not garbage-collected.
            self.window_icon_image = tk.PhotoImage(file=str(resource_path("assets/logo-taskbar.png")))
            self.master.iconphoto(True, self.window_icon_image)
        except (OSError, tk.TclError):
            self.window_icon_image = None
        self.master.geometry("1180x880")
        self.master.minsize(840, 560)
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.content_canvas = tk.Canvas(
            self,
            background=COLORS["background"],
            borderwidth=0,
            highlightthickness=0,
            takefocus=False,
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew")
        self.content_scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.content_canvas.yview,
        )
        self.content_scrollbar.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)

        self.content = ttk.Frame(self.content_canvas, style="App.TFrame")
        self.content.columnconfigure(0, weight=5, uniform="body")
        self.content.columnconfigure(1, weight=6, uniform="body")
        self.content_window = self.content_canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw",
        )
        self.content.bind("<Configure>", self._update_content_scroll_region)
        self.content_canvas.bind("<Configure>", self._resize_scroll_content)
        self.master.bind("<MouseWheel>", self._scroll_content, add="+")

        self._build_header()
        self._build_project_card()
        self._build_media_card()
        self._build_export_card()
        self._build_action_bar()

    def _build_header(self) -> None:
        header = ttk.Frame(self.content, style="Header.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.columnconfigure(1, weight=1)

        logo_path = resource_path("assets/logo-64.png")
        try:
            self.logo_image = tk.PhotoImage(file=str(logo_path))
            logo = tk.Label(header, image=self.logo_image, background=COLORS["background"])
        except tk.TclError:
            self.logo_image = None
            logo = tk.Label(
                header,
                text="S/A",
                background=COLORS["accent"],
                foreground=COLORS["accent_text"],
                font=("Segoe UI Semibold", 13),
                width=4,
                height=2,
            )
        logo.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
        ttk.Label(header, text="CapCut Hand-off Studio", style="Title.TLabel").grid(
            row=0, column=1, sticky="sw"
        )
        ttk.Label(
            header,
            text="Đồng bộ hình ảnh với audio · Xuất MP4 preview và project editable · YudgnuH (Nguyễn Duy Hưng)",
            style="Subtitle.TLabel",
        ).grid(row=1, column=1, sticky="nw", pady=(2, 0))
        self.runtime_badge = ttk.Label(
            header,
            textvariable=self.runtime_var,
            style="Badge.TLabel",
        )
        self.runtime_badge.grid(row=0, column=2, rowspan=2, sticky="e")

    def _build_project_card(self) -> None:
        card = self._card(1, 0, padx=(0, 9))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text="Thiết lập project", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            card,
            text="Chọn nguồn và vị trí lưu bản hand-off.",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 13))
        ttk.Separator(card, style="Dark.TSeparator").grid(row=2, column=0, sticky="ew")

        self._field(card, 3, "TÊN PROJECT", self.name_var)
        self._choice_field(
            card,
            4,
            "CHẾ ĐỘ ĐỒNG BỘ",
            self.alignment_var,
            list(ALIGNMENT_OPTIONS),
            self._alignment_changed,
        )
        self._field(card, 5, "AUDIO THUYẾT MINH", self.audio_var, self._choose_audio)
        self.transcript_entry, self.transcript_button = self._field(
            card,
            6,
            "TRANSCRIPT  ·  DÁN TEXT / CHỌN FILE  ·  TÁCH THEO . ! ? 。！？",
            self.transcript_var,
            self._choose_transcript,
        )
        self._field(card, 7, "THƯ MỤC ẢNH / VIDEO", self.media_dir_var, self._choose_media_dir)
        self._field(card, 8, "THƯ MỤC OUTPUT", self.output_var, self._choose_output)
        self._field(card, 9, "CAPCUT DRAFT ROOT", self.draft_root_var, self._choose_draft_root)
        self._alignment_changed()

    def _build_media_card(self) -> None:
        card = self._card(1, 1, padx=(9, 0))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)

        heading = ttk.Frame(card, style="CardInner.TFrame")
        heading.grid(row=0, column=0, sticky="ew")
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Thứ tự timeline", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(heading, textvariable=self.media_count_var, style="CardMuted.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        ttk.Label(
            card,
            text="Chọn một hàng rồi di chuyển. Cả hai chế độ đều giữ đúng thứ tự này.",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 13))
        ttk.Separator(card, style="Dark.TSeparator").grid(row=2, column=0, sticky="ew")

        table_frame = ttk.Frame(card, style="CardInner.TFrame")
        table_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.media_table = ttk.Treeview(
            table_frame,
            columns=("order", "name", "kind"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        self.media_table.heading("order", text="#")
        self.media_table.heading("name", text="TÊN FILE")
        self.media_table.heading("kind", text="LOẠI")
        self.media_table.column("order", width=48, minwidth=48, anchor="center", stretch=False)
        self.media_table.column("name", width=360, minwidth=180, anchor="w")
        self.media_table.column("kind", width=72, minwidth=72, anchor="center", stretch=False)
        self.media_table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.media_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.media_table.configure(yscrollcommand=scrollbar.set)

        toolbar = ttk.Frame(card, style="Toolbar.TFrame")
        toolbar.grid(row=4, column=0, sticky="ew")
        toolbar.columnconfigure(3, weight=1)
        ttk.Button(
            toolbar,
            text="↑  Lên",
            style="Secondary.TButton",
            command=lambda: self._move_media(-1),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            toolbar,
            text="↓  Xuống",
            style="Secondary.TButton",
            command=lambda: self._move_media(1),
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="↻  Nạp lại",
            style="Ghost.TButton",
            command=self._reload_media,
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.media_warning_label = ttk.Label(
            card,
            textvariable=self.media_warning_var,
            style="CardWarning.TLabel",
            wraplength=480,
        )
        self.media_warning_label.grid(row=5, column=0, sticky="ew", pady=(9, 0))
        self.media_warning_label.grid_remove()

    def _build_export_card(self) -> None:
        card = self._card(2, 0, columnspan=2, pady=(14, 0))
        for column in range(6):
            card.columnconfigure(column, weight=1 if column in (1, 3, 5) else 0)

        ttk.Label(card, text="Cấu hình export", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w"
        )
        ttk.Label(
            card,
            text="Một timeline duy nhất được dùng cho cả preview và CapCut draft.",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(3, 13))
        ttk.Separator(card, style="Dark.TSeparator").grid(
            row=2, column=0, columnspan=6, sticky="ew", pady=(0, 12)
        )

        ttk.Label(card, text="OUTPUT", style="Field.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Combobox(
            card,
            textvariable=self.mode_var,
            values=[mode.value for mode in OutputMode],
            state="readonly",
            width=12,
        ).grid(row=3, column=1, sticky="ew", padx=(8, 22))
        ttk.Label(card, text="CANVAS", style="Field.TLabel").grid(row=3, column=2, sticky="w")
        ttk.Combobox(
            card,
            textvariable=self.canvas_var,
            values=list(CANVAS_PRESETS),
            state="readonly",
            width=29,
        ).grid(row=3, column=3, sticky="ew", padx=(8, 22))
        ttk.Label(card, text="ẢNH / SHOT", style="Field.TLabel").grid(row=3, column=4, sticky="w")
        duration_row = ttk.Frame(card, style="CardInner.TFrame")
        duration_row.grid(row=3, column=5, sticky="ew", padx=(8, 0))
        duration_row.columnconfigure(0, weight=1)
        ttk.Entry(duration_row, textvariable=self.image_duration_var, width=7).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Label(duration_row, text="giây", style="CardMuted.TLabel").grid(
            row=0, column=1, padx=(8, 0)
        )

        checks = ttk.Frame(card, style="CardInner.TFrame")
        checks.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(13, 0))
        ttk.Checkbutton(
            checks,
            text="Motion keyframe nhẹ · zoom + pan · áp dụng cả video",
            variable=self.motion_var,
            style="Dark.TCheckbutton",
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            checks,
            text="Đăng ký project vào CapCut",
            variable=self.register_var,
            style="Dark.TCheckbutton",
        ).grid(row=0, column=1, sticky="w", padx=(24, 0))
        ttk.Checkbutton(
            checks,
            text="Burn caption vào MP4 preview",
            variable=self.burn_caption_var,
            style="Dark.TCheckbutton",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            checks,
            text="Đóng project đang mở trong CapCut trước khi tạo draft.",
            style="CardMuted.TLabel",
        ).grid(row=1, column=1, columnspan=2, sticky="e", padx=(24, 0), pady=(8, 0))
        checks.columnconfigure(2, weight=1)

    def _build_action_bar(self) -> None:
        action = ttk.Frame(self, style="Header.TFrame")
        action.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        action.columnconfigure(1, weight=1)

        status_dot = tk.Label(
            action,
            text="●",
            background=COLORS["background"],
            foreground=COLORS["accent"],
            font=("Segoe UI", 9),
        )
        status_dot.grid(row=0, column=0, sticky="w", padx=(0, 7))
        ttk.Label(action, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Button(
            action,
            text="Mở thư mục output",
            style="Secondary.TButton",
            command=lambda: self._open_folder(self.output_var.get()),
        ).grid(row=0, column=2, padx=(10, 10))
        self.build_button = ttk.Button(
            action,
            text="Tạo project  →",
            style="Accent.TButton",
            command=self._start_build,
        )
        self.build_button.grid(row=0, column=3)
        self.progress = ttk.Progressbar(
            action,
            mode="determinate",
            maximum=100,
            style="Accent.Horizontal.TProgressbar",
        )
        self.progress.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

    def _card(
        self,
        row: int,
        column: int,
        *,
        columnspan: int = 1,
        padx: tuple[int, int] = (0, 0),
        pady: tuple[int, int] = (0, 0),
    ) -> ttk.Frame:
        card = ttk.Frame(self.content, style="Card.TFrame", padding=(18, 13))
        card.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="nsew",
            padx=padx,
            pady=pady,
        )
        return card

    def _update_content_scroll_region(self, _event=None) -> None:
        bounds = self.content_canvas.bbox(self.content_window)
        if bounds:
            self.content_canvas.configure(scrollregion=bounds)

    def _resize_scroll_content(self, event: tk.Event) -> None:
        self.content_canvas.itemconfigure(self.content_window, width=max(1, event.width))

    def _scroll_content(self, event: tk.Event) -> str | None:
        # Preserve the media table's own scrolling when the pointer is over it.
        widget = event.widget
        if widget is self.media_table or widget.winfo_class() in {"Treeview", "TCombobox"}:
            return None
        delta = int(getattr(event, "delta", 0))
        if not delta:
            return None
        self.content_canvas.yview_scroll(-1 if delta > 0 else 1, "units")
        return "break"

    def _field(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command=None,
    ) -> tuple[ttk.Entry, ttk.Button | None]:
        wrapper = ttk.Frame(parent, style="CardInner.TFrame")
        wrapper.grid(row=row, column=0, sticky="ew", pady=(7, 0))
        wrapper.columnconfigure(0, weight=1)
        ttk.Label(wrapper, text=label, style="Field.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 3)
        )
        entry = ttk.Entry(wrapper, textvariable=variable)
        entry.grid(row=1, column=0, sticky="ew")
        button: ttk.Button | None = None
        if command:
            button = ttk.Button(
                wrapper,
                text="Chọn…",
                style="Secondary.TButton",
                command=command,
            )
            button.grid(row=1, column=1, padx=(8, 0))
        return entry, button

    def _choice_field(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: list[str],
        command,
    ) -> None:
        wrapper = ttk.Frame(parent, style="CardInner.TFrame")
        wrapper.grid(row=row, column=0, sticky="ew", pady=(7, 0))
        wrapper.columnconfigure(0, weight=1)
        ttk.Label(wrapper, text=label, style="Field.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 3)
        )
        combo = ttk.Combobox(
            wrapper,
            textvariable=variable,
            values=values,
            state="readonly",
        )
        combo.grid(row=1, column=0, sticky="ew")
        combo.bind("<<ComboboxSelected>>", lambda _event: command())

    def _choose_audio(self) -> None:
        value = filedialog.askopenfilename(
            title="Chọn audio thuyết minh",
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("Tất cả", "*.*")],
        )
        if value:
            self.audio_var.set(value)

    def _choose_media_dir(self) -> None:
        value = filedialog.askdirectory(title="Chọn thư mục ảnh và video")
        if value:
            self.media_dir_var.set(value)
            self._reload_media()

    def _choose_transcript(self) -> None:
        value = filedialog.askopenfilename(
            title="Chọn transcript của voice",
            filetypes=[
                ("Transcript", "*.txt *.srt *.json"),
                ("Text", "*.txt"),
                ("Subtitle", "*.srt"),
                ("JSON", "*.json"),
                ("Tất cả", "*.*"),
            ],
        )
        if value:
            self.transcript_var.set(value)

    def _alignment_changed(self) -> None:
        enabled = ALIGNMENT_OPTIONS[self.alignment_var.get()] is AlignmentMode.TRANSCRIPT
        self.transcript_entry.configure(state="normal" if enabled else "disabled")
        if self.transcript_button:
            self.transcript_button.configure(state="normal" if enabled else "disabled")

    def _choose_output(self) -> None:
        value = filedialog.askdirectory(title="Chọn thư mục output")
        if value:
            self.output_var.set(value)

    def _choose_draft_root(self) -> None:
        value = filedialog.askdirectory(title="Chọn CapCut Draft root")
        if value:
            self.draft_root_var.set(value)

    def _reload_media(self) -> None:
        try:
            self.media_paths = sort_media(self.media_dir_var.get())
        except (OSError, ValueError) as error:
            self.media_paths = []
            messagebox.showerror("Không nạp được media", str(error), parent=self.master)
        self._refresh_media_table()

    def _refresh_media_table(self, selected_index: int | None = None) -> None:
        self.media_table.delete(*self.media_table.get_children())
        for index, path in enumerate(self.media_paths):
            kind = MEDIA_TYPE_LABELS.get(path.suffix.lower(), "VIDEO")
            self.media_table.insert(
                "",
                tk.END,
                iid=str(index),
                values=(f"{index + 1:02d}", path.name, kind),
            )
        count = len(self.media_paths)
        self.media_count_var.set(f"{count} media" if count else "Chưa có media")
        report = inspect_media_numbering(self.media_paths)
        warnings: list[str] = []
        if report.missing_numbers:
            values = ", ".join(f"{number:03d}" for number in report.missing_numbers[:12])
            if len(report.missing_numbers) > 12:
                values += ", …"
            warnings.append(f"Thiếu số file: {values}")
        if report.duplicate_numbers:
            values = ", ".join(f"{number:03d}" for number in report.duplicate_numbers[:12])
            warnings.append(f"Trùng số file: {values}")
        self.media_warning_var.set("  ·  ".join(warnings))
        if warnings:
            self.media_warning_label.grid()
        else:
            self.media_warning_label.grid_remove()
        if selected_index is not None and 0 <= selected_index < count:
            item = str(selected_index)
            self.media_table.selection_set(item)
            self.media_table.focus(item)
            self.media_table.see(item)

    def _move_media(self, delta: int) -> None:
        selection = self.media_table.selection()
        if not selection:
            return
        current = self.media_table.index(selection[0])
        target = current + delta
        if not 0 <= target < len(self.media_paths):
            return
        self.media_paths[current], self.media_paths[target] = (
            self.media_paths[target],
            self.media_paths[current],
        )
        self._refresh_media_table(target)

    def _detect_runtime(self) -> None:
        capcut_ready = False
        try:
            registry = CapCutRegistry.discover()
            if registry:
                self.draft_root_var.set(str(registry.draft_root()))
                capcut_ready = True
        except (OSError, ValueError):
            pass
        ffmpeg_ready = Path(resolve_executable("ffmpeg")).is_file() and Path(
            resolve_executable("ffprobe")
        ).is_file()
        try:
            from .transcription import _faster_whisper
            whisper_ready = True
            if _faster_whisper is None:
                raise ImportError
        except ImportError:
            whisper_ready = Path(resolve_executable("whisper")).is_file()
        if capcut_ready and ffmpeg_ready and whisper_ready:
            self.runtime_var.set("●  CapCut + FFmpeg + Whisper")
            self.runtime_badge.configure(style="Badge.TLabel")
        elif capcut_ready:
            missing = "Whisper" if ffmpeg_ready else "FFmpeg"
            self.runtime_var.set(f"!  Thiếu {missing}")
            self.runtime_badge.configure(style="WarningBadge.TLabel")
        else:
            self.runtime_var.set("!  Chưa phát hiện CapCut")
            self.runtime_badge.configure(style="WarningBadge.TLabel")

    def _start_build(self) -> None:
        try:
            request = self._collect_request()
        except (OSError, ValueError) as error:
            messagebox.showerror("Thiếu hoặc sai dữ liệu", str(error), parent=self.master)
            return
        self.build_button.configure(state="disabled", text="Đang xử lý…")
        self.progress.grid()
        self.progress.configure(value=0)
        if ALIGNMENT_OPTIONS[self.alignment_var.get()] is AlignmentMode.TRANSCRIPT:
            # Model construction is not measurable and can take a few minutes
            # on a CPU-only machine. Keep the UI visibly alive until Whisper
            # starts yielding timestamp progress.
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.configure(mode="determinate")
        if ALIGNMENT_OPTIONS[self.alignment_var.get()] is AlignmentMode.TRANSCRIPT:
            self.status_var.set("Whisper đang lấy timestamp và căn transcript…")
        else:
            self.status_var.set("Đang lập timeline và tạo output…")
        threading.Thread(target=self._worker, args=(request,), daemon=True).start()

    def _collect_request(self) -> dict[str, object]:
        name = self.name_var.get().strip()
        if not name:
            raise ValueError("Tên project không được để trống")
        if not self.media_paths:
            self._reload_media()
        if not self.media_paths:
            raise ValueError("Chưa có ảnh hoặc video trong timeline")
        duration = float(self.image_duration_var.get())
        if duration <= 0:
            raise ValueError("Thời lượng ảnh/shot phải lớn hơn 0 giây")
        alignment_mode = ALIGNMENT_OPTIONS[self.alignment_var.get()]
        transcript = self.transcript_var.get().strip()
        if alignment_mode is AlignmentMode.TRANSCRIPT and not transcript:
            raise ValueError("Chế độ căn chuẩn cần dán text hoặc chọn file transcript")
        transcript_path: Path | None = None
        transcript_text: str | None = None
        if alignment_mode is AlignmentMode.TRANSCRIPT and transcript:
            try:
                candidate = Path(transcript)
                is_file = candidate.is_file()
            except OSError:
                candidate = None
                is_file = False
            if is_file:
                transcript_path = candidate
            elif candidate is not None and candidate.suffix.lower() in {
                ".txt",
                ".srt",
                ".json",
            } and ("\\" in transcript or "/" in transcript):
                raise FileNotFoundError(f"Transcript không tồn tại: {candidate}")
            else:
                transcript_text = transcript
        return {
            "name": name,
            "audio": Path(self.audio_var.get()),
            "media_dir": Path(self.media_dir_var.get()),
            "alignment_mode": alignment_mode,
            "transcript_path": transcript_path,
            "transcript_text": transcript_text,
            "ordered": list(self.media_paths),
            "output": Path(self.output_var.get()),
            "draft_root": (
                Path(self.draft_root_var.get()) if self.draft_root_var.get().strip() else None
            ),
            "mode": OutputMode(self.mode_var.get()),
            "canvas": CANVAS_PRESETS[self.canvas_var.get()],
            "image_duration": seconds_to_us(duration),
            "motion": self.motion_var.get(),
            "burn_captions": self.burn_caption_var.get(),
            "register": self.register_var.get(),
        }

    def _worker(self, request: dict[str, object]) -> None:
        try:
            project = build_timeline(
                project_name=str(request["name"]),
                audio_path=request["audio"],
                media_dir=request["media_dir"],
                ordered_media_paths=request["ordered"],
                alignment_mode=request["alignment_mode"],
                transcript_path=request["transcript_path"],
                transcript_text=request["transcript_text"],
                whisper_config=WhisperConfig(model="small"),
                progress_callback=lambda value, message: self._emit_progress(
                    0.02 + value * 0.18, message
                ),
                config=PlannerConfig(
                    canvas=request["canvas"],
                    image_shot_duration_us=int(request["image_duration"]),
                    motion_enabled=bool(request["motion"]),
                ),
            )
            outputs = export_timeline(
                project,
                mode=request["mode"],
                output_dir=request["output"],
                draft_root=request["draft_root"],
                register_with_capcut=bool(request["register"]),
                burn_captions=bool(request["burn_captions"]),
                progress_callback=lambda value, message: self._emit_progress(
                    0.20 + value * 0.80, message
                ),
            )
            self.events.put(("done", outputs))
        except BaseException as error:
            self.events.put(("error", error))

    def _emit_progress(self, value: float, message: str) -> None:
        self.events.put(("progress", (value, message)))

    def _poll_events(self) -> None:
        try:
            kind, payload = self.events.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_events)
            return
        if kind == "progress":
            value, message = payload
            if self.progress.cget("mode") == "indeterminate" and "timestamp" in str(message).lower():
                self.progress.stop()
                self.progress.configure(mode="determinate")
            self.progress.configure(value=float(value) * 100)
            self.status_var.set(str(message))
            self.after(100, self._poll_events)
            return
        self.progress.stop()
        self.progress.grid_remove()
        self.build_button.configure(state="normal", text="Tạo project  →")
        if kind == "done":
            outputs = payload
            assert isinstance(outputs, PipelineOutputs)
            lines = [f"Manifest\n{outputs.manifest}"]
            if outputs.mp4:
                lines.append(f"MP4 preview\n{outputs.mp4}")
            if outputs.capcut:
                lines.append(f"CapCut project\n{outputs.capcut.draft_folder}")
            self.status_var.set("Hoàn tất · Project đã sẵn sàng để bàn giao")
            messagebox.showinfo(
                "Đã tạo project thành công",
                "\n\n".join(lines),
                parent=self.master,
            )
        else:
            self.status_var.set("Có lỗi · Kiểm tra lại dữ liệu đầu vào")
            messagebox.showerror(
                "Không tạo được project",
                str(payload),
                parent=self.master,
            )
        self.after(100, self._poll_events)

    @staticmethod
    def _open_folder(value: str) -> None:
        path = Path(value).resolve()
        path.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Output", str(path))


def _center_window(root: tk.Tk, width: int = 1180, height: int = 880) -> None:
    root.update_idletasks()
    width = min(width, max(840, root.winfo_screenwidth() - 48))
    height = min(height, max(560, root.winfo_screenheight() - 96))
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")


def launch() -> None:
    configure_runtime_storage()
    _set_windows_app_user_model_id()
    root = tk.Tk()
    SyncVideoAudioApp(root)
    _center_window(root)
    root.mainloop()


def _set_windows_app_user_model_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "YudgnuH.SyncVideoAudio"
        )
    except (AttributeError, OSError):
        pass


if __name__ == "__main__":
    launch()

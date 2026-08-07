"""Tk desktop application for MP4 and editable CapCut hand-offs."""

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
from .planner import PlannerConfig, build_timeline, sort_media


CANVAS_PRESETS = {
    "Dọc 9:16 — 1080 × 1920": CanvasSpec(1080, 1920, 30),
    "Ngang 16:9 — 1920 × 1080": CanvasSpec(1920, 1080, 30),
    "Vuông 1:1 — 1080 × 1080": CanvasSpec(1080, 1080, 30),
}


class SyncVideoAudioApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=18)
        self.master = master
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.media_paths: list[Path] = []
        self._build_variables()
        self._build_ui()
        self._detect_capcut()
        self.after(100, self._poll_events)

    def _build_variables(self) -> None:
        self.name_var = tk.StringVar(value="Video mới")
        self.audio_var = tk.StringVar()
        self.media_dir_var = tk.StringVar()
        self.mapping_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str((Path.cwd() / "output").resolve()))
        self.draft_root_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=OutputMode.BOTH.value)
        self.canvas_var = tk.StringVar(value=next(iter(CANVAS_PRESETS)))
        self.image_duration_var = tk.StringVar(value="6")
        self.motion_var = tk.BooleanVar(value=True)
        self.register_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Sẵn sàng")

    def _build_ui(self) -> None:
        self.master.title("SyncVideo-Audio · CapCut Hand-off")
        self.master.geometry("980x760")
        self.master.minsize(820, 650)
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(7, weight=1)

        ttk.Label(
            self,
            text="Sync ảnh/video theo audio → MP4 + CapCut editable",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        self._entry_row(1, "Tên project", self.name_var)
        self._entry_row(2, "Audio thuyết minh", self.audio_var, self._choose_audio)
        self._entry_row(3, "Thư mục ảnh/video", self.media_dir_var, self._choose_media_dir)
        self._entry_row(4, "Scene mapping (tuỳ chọn)", self.mapping_var, self._choose_mapping)
        self._entry_row(5, "Thư mục output", self.output_var, self._choose_output)
        self._entry_row(6, "CapCut Draft root", self.draft_root_var, self._choose_draft_root)

        media_frame = ttk.LabelFrame(
            self,
            text="Thứ tự media (scene mapping sẽ quyết định thứ tự nếu được chọn)",
            padding=10,
        )
        media_frame.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(12, 8))
        media_frame.columnconfigure(0, weight=1)
        media_frame.rowconfigure(0, weight=1)
        self.media_list = tk.Listbox(media_frame, selectmode=tk.SINGLE, activestyle="dotbox")
        self.media_list.grid(row=0, column=0, rowspan=4, sticky="nsew")
        scrollbar = ttk.Scrollbar(media_frame, orient="vertical", command=self.media_list.yview)
        scrollbar.grid(row=0, column=1, rowspan=4, sticky="ns")
        self.media_list.configure(yscrollcommand=scrollbar.set)
        ttk.Button(media_frame, text="Lên", command=lambda: self._move_media(-1)).grid(
            row=0, column=2, padx=(10, 0), sticky="ew"
        )
        ttk.Button(media_frame, text="Xuống", command=lambda: self._move_media(1)).grid(
            row=1, column=2, padx=(10, 0), sticky="ew"
        )
        ttk.Button(media_frame, text="Nạp lại", command=self._reload_media).grid(
            row=2, column=2, padx=(10, 0), sticky="ew"
        )

        options = ttk.Frame(self)
        options.grid(row=8, column=0, columnspan=3, sticky="ew", pady=8)
        for index in range(6):
            options.columnconfigure(index, weight=1 if index in (1, 3, 5) else 0)
        ttk.Label(options, text="Output").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            options,
            textvariable=self.mode_var,
            values=[mode.value for mode in OutputMode],
            state="readonly",
            width=10,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 16))
        ttk.Label(options, text="Canvas").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            options,
            textvariable=self.canvas_var,
            values=list(CANVAS_PRESETS),
            state="readonly",
            width=28,
        ).grid(row=0, column=3, sticky="ew", padx=(6, 16))
        ttk.Label(options, text="Ảnh/shot (giây)").grid(row=0, column=4, sticky="w")
        ttk.Entry(options, textvariable=self.image_duration_var, width=8).grid(
            row=0, column=5, sticky="ew", padx=(6, 0)
        )
        ttk.Checkbutton(options, text="Motion keyframe nhẹ", variable=self.motion_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(
            options,
            text="Đăng ký project vào CapCut",
            variable=self.register_var,
        ).grid(row=1, column=2, columnspan=3, sticky="w", pady=(8, 0))

        action = ttk.Frame(self)
        action.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        action.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(action, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.build_button = ttk.Button(action, text="Tạo hand-off", command=self._start_build)
        self.build_button.grid(row=0, column=1)
        ttk.Button(
            action,
            text="Mở output",
            command=lambda: self._open_folder(self.output_var.get()),
        ).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(self, textvariable=self.status_var).grid(
            row=10, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Label(
            self,
            text="Lưu ý: đóng project đang mở trong CapCut trước khi tạo/đăng ký draft.",
            foreground="#a15c00",
        ).grid(row=11, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _entry_row(self, row: int, label: str, variable: tk.StringVar, command=None) -> None:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(self, textvariable=variable).grid(
            row=row, column=1, sticky="ew", padx=10, pady=4
        )
        if command:
            ttk.Button(self, text="Chọn…", command=command).grid(
                row=row, column=2, sticky="ew", pady=4
            )

    def _choose_audio(self) -> None:
        value = filedialog.askopenfilename(
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("Tất cả", "*.*")]
        )
        if value:
            self.audio_var.set(value)

    def _choose_media_dir(self) -> None:
        value = filedialog.askdirectory()
        if value:
            self.media_dir_var.set(value)
            self._reload_media()

    def _choose_mapping(self) -> None:
        value = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("Tất cả", "*.*")]
        )
        if value:
            self.mapping_var.set(value)

    def _choose_output(self) -> None:
        value = filedialog.askdirectory()
        if value:
            self.output_var.set(value)

    def _choose_draft_root(self) -> None:
        value = filedialog.askdirectory()
        if value:
            self.draft_root_var.set(value)

    def _reload_media(self) -> None:
        try:
            self.media_paths = sort_media(self.media_dir_var.get())
        except (OSError, ValueError) as error:
            self.media_paths = []
            messagebox.showerror("Không nạp được media", str(error))
        self._refresh_media_list()

    def _refresh_media_list(self) -> None:
        self.media_list.delete(0, tk.END)
        for index, path in enumerate(self.media_paths, 1):
            self.media_list.insert(tk.END, f"{index:03d} · {path.name}")

    def _move_media(self, delta: int) -> None:
        selection = self.media_list.curselection()
        if not selection:
            return
        current = selection[0]
        target = current + delta
        if not 0 <= target < len(self.media_paths):
            return
        self.media_paths[current], self.media_paths[target] = (
            self.media_paths[target],
            self.media_paths[current],
        )
        self._refresh_media_list()
        self.media_list.selection_set(target)
        self.media_list.see(target)

    def _detect_capcut(self) -> None:
        try:
            registry = CapCutRegistry.discover()
            if registry:
                self.draft_root_var.set(str(registry.draft_root()))
        except (OSError, ValueError):
            pass

    def _start_build(self) -> None:
        try:
            request = self._collect_request()
        except (OSError, ValueError) as error:
            messagebox.showerror("Thiếu hoặc sai dữ liệu", str(error))
            return
        self.build_button.configure(state="disabled")
        self.progress.start(12)
        self.status_var.set("Đang lập timeline và tạo output…")
        threading.Thread(target=self._worker, args=(request,), daemon=True).start()

    def _collect_request(self) -> dict[str, object]:
        name = self.name_var.get().strip()
        if not name:
            raise ValueError("Tên project không được để trống")
        if not self.media_paths:
            self._reload_media()
        if not self.media_paths:
            raise ValueError("Chưa có media")
        duration = float(self.image_duration_var.get())
        if duration <= 0:
            raise ValueError("Ảnh/shot phải lớn hơn 0 giây")
        mapping = self.mapping_var.get().strip()
        return {
            "name": name,
            "audio": Path(self.audio_var.get()),
            "media_dir": Path(self.media_dir_var.get()),
            "mapping": Path(mapping) if mapping else None,
            "ordered": None if mapping else list(self.media_paths),
            "output": Path(self.output_var.get()),
            "draft_root": (
                Path(self.draft_root_var.get())
                if self.draft_root_var.get().strip()
                else None
            ),
            "mode": OutputMode(self.mode_var.get()),
            "canvas": CANVAS_PRESETS[self.canvas_var.get()],
            "image_duration": seconds_to_us(duration),
            "motion": self.motion_var.get(),
            "register": self.register_var.get(),
        }

    def _worker(self, request: dict[str, object]) -> None:
        try:
            project = build_timeline(
                project_name=str(request["name"]),
                audio_path=request["audio"],
                media_dir=request["media_dir"],
                mapping_path=request["mapping"],
                ordered_media_paths=request["ordered"],
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
            )
            self.events.put(("done", outputs))
        except BaseException as error:
            self.events.put(("error", error))

    def _poll_events(self) -> None:
        try:
            kind, payload = self.events.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_events)
            return
        self.progress.stop()
        self.build_button.configure(state="normal")
        if kind == "done":
            outputs = payload
            assert isinstance(outputs, PipelineOutputs)
            lines = [f"Manifest: {outputs.manifest}"]
            if outputs.mp4:
                lines.append(f"MP4: {outputs.mp4}")
            if outputs.capcut:
                lines.append(f"CapCut: {outputs.capcut.draft_folder}")
            self.status_var.set("Hoàn tất")
            messagebox.showinfo("Đã tạo hand-off", "\n".join(lines))
        else:
            self.status_var.set("Có lỗi")
            messagebox.showerror("Không tạo được hand-off", str(payload))
        self.after(100, self._poll_events)

    @staticmethod
    def _open_folder(value: str) -> None:
        path = Path(value).resolve()
        path.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Output", str(path))


def launch() -> None:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    SyncVideoAudioApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch()

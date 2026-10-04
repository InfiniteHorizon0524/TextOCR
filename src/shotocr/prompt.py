"""A small confirmation dialog for a newly copied image."""

from __future__ import annotations

from pathlib import Path

from . import core


def ask_ocr(expected_digest: str, stop_file: Path | None = None) -> bool | None:
    """Return True for yes, False for no, or None if the image becomes stale."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.withdraw()
    answer: bool | None = None
    try:
        dialog = tk.Toplevel(root)
        dialog.title("截图 OCR")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        width, height = 360, 150
        x = max(0, root.winfo_screenwidth() - width - 24)
        y = max(0, root.winfo_screenheight() - height - 72)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="发现新的剪贴板图片", font=("", 12, "bold")).pack(anchor="w")
        ttk.Label(body, text="需要进行 OCR 识别吗？").pack(anchor="w", pady=(10, 12))
        buttons = ttk.Frame(body)
        buttons.pack(anchor="e")

        def choose(value: bool | None) -> None:
            nonlocal answer
            answer = value
            dialog.destroy()

        ttk.Button(buttons, text="否，跳过", command=lambda: choose(False)).pack(side="left", padx=(0, 8))
        yes_button = ttk.Button(buttons, text="是，识别", command=lambda: choose(True))
        yes_button.pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(False))
        dialog.bind("<Escape>", lambda _event: choose(False))
        dialog.bind("<Return>", lambda _event: choose(True))

        def check_current_image() -> None:
            if stop_file is not None and stop_file.exists():
                choose(None)
                return
            try:
                image = core.clipboard_image()
                if image is None or core.image_digest(core.image_png(image)) != expected_digest:
                    choose(None)
                    return
            except core.ShotOCRError:
                pass  # A clipboard owner can temporarily block reads.
            dialog.after(1000, check_current_image)

        dialog.after(1000, check_current_image)
        dialog.wait_visibility()
        dialog.lift()
        dialog.focus_force()
        yes_button.focus_set()
        dialog.grab_set()
        root.wait_window(dialog)
        return answer
    finally:
        root.destroy()

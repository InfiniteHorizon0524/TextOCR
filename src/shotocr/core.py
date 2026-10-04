"""Clipboard, OCR and persistent history operations."""

from __future__ import annotations

import hashlib
import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageGrab
from platformdirs import user_data_path


class ShotOCRError(Exception):
    """An expected user-facing failure."""


def default_home() -> Path:
    # Editable installs keep the model and database next to this project.
    project = Path(__file__).resolve().parents[2]
    if (project / "pyproject.toml").is_file():
        return project / ".local"
    return user_data_path("shotocr", "shotocr")


def clipboard_image() -> Image.Image | None:
    try:
        value = ImageGrab.grabclipboard()
    except (OSError, NotImplementedError) as exc:
        raise ShotOCRError(f"无法读取图片剪贴板：{exc}") from exc
    return value.copy() if isinstance(value, Image.Image) else None


def image_png(image: Image.Image) -> bytes:
    with io.BytesIO() as buffer:
        image.convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue()


def image_digest(png: bytes) -> str:
    return hashlib.sha256(png).hexdigest()


def recognize(png: bytes, models_dir: Path) -> str:
    from rapidocr import RapidOCR

    models_dir.mkdir(parents=True, exist_ok=True)
    engine = RapidOCR(params={
        "Global.model_root_dir": str(models_dir.resolve()),
        "Global.log_level": "error",
    })
    result = engine(png)
    return "\n".join(line.strip() for line in (result.txts or ()) if line.strip())


def save_history(db_path: Path, text: str, digest: str, source: str) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            image_sha256 TEXT NOT NULL,
            text TEXT NOT NULL
        )""")
        cursor = db.execute(
            "INSERT INTO history (created_at, source, image_sha256, text) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), source, digest, text),
        )
        return int(cursor.lastrowid)


def read_history(db_path: Path, limit: int) -> list[tuple[int, str, str, str]]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as db:
        return db.execute(
            "SELECT id, created_at, source, text FROM history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def copy_text(text: str) -> None:
    import pyperclip

    try:
        pyperclip.copy(text)
    except (OSError, RuntimeError, pyperclip.PyperclipException) as exc:
        raise ShotOCRError(f"识别成功，但复制到剪贴板失败：{exc}") from exc


def notify(message: str) -> None:
    import asyncio
    from desktop_notifier import DesktopNotifier

    async def send() -> None:
        await DesktopNotifier(app_name="ShotOCR").send(title="截图 OCR", message=message)

    asyncio.run(send())

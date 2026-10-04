"""Command line interface and clipboard watcher."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

from . import core, prompt


def process(image: Image.Image, home: Path, *, source: str, copy: bool, notification: bool) -> str:
    png = core.image_png(image)
    text = core.recognize(png, home / "models")
    if not text:
        raise core.ShotOCRError("图片中没有识别出文本，未写入历史记录。")
    record_id = core.save_history(home / "history.sqlite3", text, core.image_digest(png), source)
    copied = False
    if copy:
        try:
            core.copy_text(text)
            copied = True
        except core.ShotOCRError as exc:
            print(f"警告：{exc}", file=sys.stderr)
    if notification:
        try:
            preview = text.replace("\n", " ")[:100]
            prefix = "已复制到剪贴板" if copied else "已保存到历史记录"
            core.notify(f"{prefix}（#{record_id}）：{preview}")
        except Exception as exc:  # A notification must not discard successful OCR.
            print(f"警告：桌面通知失败：{exc}", file=sys.stderr)
    return text


def watch(home: Path, interval: float, *, copy: bool, notification: bool, stop_file: Path | None = None) -> int:
    previous_digest: str | None = None
    print("正在监听剪贴板图片。按 Ctrl+C 停止。", file=sys.stderr)
    try:
        while True:
            if stop_file is not None and stop_file.exists():
                return 0
            try:
                image = core.clipboard_image()
                if image is None:
                    previous_digest = None
                else:
                    digest = core.image_digest(core.image_png(image))
                    if digest != previous_digest:
                        previous_digest = digest
                        try:
                            decision = prompt.ask_ocr(digest, stop_file)
                            if decision:
                                latest = core.clipboard_image()
                                if latest is not None and core.image_digest(core.image_png(latest)) == digest:
                                    print(process(latest, home, source="clipboard", copy=copy, notification=notification), flush=True)
                        except core.ShotOCRError as exc:
                            print(f"警告：{exc}", file=sys.stderr)
                        except Exception as exc:
                            print(f"警告：确认弹窗或识别失败：{exc}", file=sys.stderr)
                        if stop_file is not None and stop_file.exists():
                            return 0
            except Exception as exc:
                print(f"警告：{exc}", file=sys.stderr)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("监听已停止。", file=sys.stderr)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shotocr", description="本地截图 OCR 工具")
    parser.add_argument("--home", type=Path, default=core.default_home(), help="模型和 SQLite 历史目录")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("once", "识别当前剪贴板图片"), ("watch", "持续监听剪贴板图片")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--no-copy", action="store_true", help="不将识别文本复制到剪贴板")
        command.add_argument("--no-notify", action="store_true", help="不显示桌面通知")
        if name == "watch":
            command.add_argument("--interval", type=float, default=5.0, help="轮询间隔秒数，默认 5")
    starter = sub.add_parser("start", help="在后台启动监听")
    starter.add_argument("--interval", type=float, default=5.0, help="轮询间隔秒数，默认 5")
    sub.add_parser("stop", help="停止后台监听")
    sub.add_parser("status", help="查看后台监听状态")
    worker = sub.add_parser("_worker", help="后台进程内部命令")
    worker.add_argument("--interval", type=float, required=True)
    history = sub.add_parser("history", help="查看最近的识别记录")
    history.add_argument("--limit", type=int, default=20, help="显示条数，默认 20")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = args.home.expanduser().resolve()
    if args.command in {"start", "watch", "_worker"} and args.interval <= 0:
        print("错误：--interval 必须大于 0。", file=sys.stderr)
        return 2
    if args.command in {"start", "stop", "status", "_worker"}:
        from . import background

        if args.command == "start":
            return background.start(home, args.interval)
        if args.command == "stop":
            return background.stop(home)
        if args.command == "status":
            return background.status(home)
        return background.run_worker(home, args.interval)
    if args.command == "history":
        if args.limit < 1:
            print("错误：--limit 必须大于 0。", file=sys.stderr)
            return 2
        for record_id, timestamp, source, value in core.read_history(home / "history.sqlite3", args.limit):
            print(f"#{record_id} {timestamp} [{source}]\n{value}\n")
        return 0
    if args.command == "watch":
        return watch(home, args.interval, copy=not args.no_copy, notification=not args.no_notify)
    try:
        image = core.clipboard_image()
        if image is None:
            raise core.ShotOCRError("剪贴板中没有图片。请先截图并复制图片。")
        print(process(image, home, source="clipboard", copy=not args.no_copy, notification=not args.no_notify))
        return 0
    except (core.ShotOCRError, OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

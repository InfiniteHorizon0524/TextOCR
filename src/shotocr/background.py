"""Manage the detached clipboard watcher."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil


def _paths(home: Path) -> tuple[Path, Path, Path, Path]:
    return (
        home / "worker.json",
        home / "worker.ready",
        home / "worker.stop",
        home / "worker.log",
    )


def _read_state(home: Path) -> dict | None:
    state_file = _paths(home)[0]
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return None


def _active_state(home: Path) -> dict | None:
    state = _read_state(home)
    if not state:
        return None
    try:
        process = psutil.Process(int(state["pid"]))
        if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
            if abs(process.create_time() - float(state["created_at"])) < 0.1:
                return state
    except (psutil.Error, KeyError, TypeError, ValueError):
        pass
    return None


def start(home: Path, interval: float) -> int:
    home.mkdir(parents=True, exist_ok=True)
    state_file, ready_file, stop_file, log_file = _paths(home)
    state = _active_state(home)
    if state:
        print(f"后台 OCR 已在运行（PID {state['pid']}，间隔 {state['interval']} 秒）。")
        return 0
    for path in (state_file, ready_file, stop_file):
        path.unlink(missing_ok=True)

    executable = Path(sys.executable)
    if os.name == "nt":
        windowless = executable.with_name("pythonw.exe")
        if windowless.exists():
            executable = windowless
    command = [str(executable), "-m", "shotocr", "--home", str(home), "_worker", "--interval", str(interval)]
    kwargs = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
    }
    with log_file.open("ab") as log:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            close_fds=True, **kwargs,
        )
    state_file.write_text(json.dumps({
        "pid": process.pid,
        "created_at": psutil.Process(process.pid).create_time(),
        "interval": interval,
    }), encoding="utf-8")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if ready_file.exists():
            try:
                worker_pid = int(ready_file.read_text(encoding="ascii"))
                worker = psutil.Process(worker_pid)
                if worker.is_running():
                    # A Windows venv pythonw.exe launcher may create a second process.
                    state_file.write_text(json.dumps({
                        "pid": worker_pid,
                        "created_at": worker.create_time(),
                        "interval": interval,
                    }), encoding="utf-8")
                    print(f"后台 OCR 已启动（PID {worker_pid}，每 {interval:g} 秒检查一次）。")
                    return 0
            except (ValueError, OSError, psutil.Error):
                pass
        time.sleep(0.1)
    print(f"后台进程未能启动，请查看日志：{log_file}", file=sys.stderr)
    return 1


def stop(home: Path) -> int:
    state = _active_state(home)
    if not state:
        print("后台 OCR 未运行。")
        return 0
    _paths(home)[2].write_text("stop", encoding="ascii")
    deadline = time.monotonic() + max(12, float(state["interval"]) + 5)
    while time.monotonic() < deadline:
        if _active_state(home) is None:
            print("后台 OCR 已停止。")
            return 0
        time.sleep(0.2)
    print("已发出停止请求；进程仍在运行，可能正在识别图片。", file=sys.stderr)
    return 1


def status(home: Path) -> int:
    state = _active_state(home)
    if state:
        print(f"后台 OCR 正在运行（PID {state['pid']}，间隔 {state['interval']} 秒）。")
    else:
        print("后台 OCR 未运行。")
    return 0


def run_worker(home: Path, interval: float) -> int:
    from .cli import watch

    state_file, ready_file, stop_file, _ = _paths(home)
    ready_file.write_text(str(os.getpid()), encoding="ascii")
    try:
        return watch(home, interval, copy=True, notification=True, stop_file=stop_file)
    finally:
        state = _read_state(home)
        if state and state.get("pid") == os.getpid():
            state_file.unlink(missing_ok=True)
            if ready_file.exists() and ready_file.read_text(encoding="ascii") == str(os.getpid()):
                ready_file.unlink(missing_ok=True)
            stop_file.unlink(missing_ok=True)

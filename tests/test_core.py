import sqlite3

from PIL import Image

from shotocr import core, prompt
from shotocr.cli import main, process


def test_process_saves_and_copies(monkeypatch, tmp_path):
    image = Image.new("RGB", (80, 40), "white")
    copied = []
    notified = []
    monkeypatch.setattr(core, "recognize", lambda png, models: "你好\nWorld")
    monkeypatch.setattr(core, "copy_text", copied.append)
    monkeypatch.setattr(core, "notify", notified.append)

    assert process(image, tmp_path, source="clipboard", copy=True, notification=True) == "你好\nWorld"
    assert copied == ["你好\nWorld"]
    assert len(notified) == 1
    assert len(core.read_history(tmp_path / "history.sqlite3", 10)) == 1
    with sqlite3.connect(tmp_path / "history.sqlite3") as db:
        digest, value = db.execute("SELECT image_sha256, text FROM history").fetchone()
    assert digest == core.image_digest(core.image_png(image))
    assert value == "你好\nWorld"


def test_no_text_does_not_save(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "recognize", lambda png, models: "")
    assert main(["--home", str(tmp_path), "history"]) == 0
    import pytest
    with pytest.raises(core.ShotOCRError):
        process(Image.new("RGB", (10, 10)), tmp_path, source="clipboard", copy=False, notification=False)
    assert not (tmp_path / "history.sqlite3").exists()


def test_once_without_image(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(core, "clipboard_image", lambda: None)
    assert main(["--home", str(tmp_path), "once"]) == 1
    assert "没有图片" in capsys.readouterr().err


def test_watch_same_image_after_text_clipboard(monkeypatch, tmp_path, capsys):
    from shotocr import cli

    image = Image.new("RGB", (10, 10), "white")
    clipboard = iter([image, image, None, image, image])
    monkeypatch.setattr(core, "clipboard_image", lambda: next(clipboard))
    monkeypatch.setattr(prompt, "ask_ocr", lambda *args: True)
    monkeypatch.setattr(cli, "process", lambda *args, **kwargs: "text")
    calls = []

    def fake_sleep(seconds):
        calls.append(seconds)
        if len(calls) == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    assert cli.watch(tmp_path, 0.1, copy=False, notification=False) == 0
    assert capsys.readouterr().out.count("text") == 2


def test_watch_no_skips_ocr_without_reprompting(monkeypatch, tmp_path):
    from shotocr import cli

    image = Image.new("RGB", (10, 10), "white")
    monkeypatch.setattr(core, "clipboard_image", lambda: image)
    answers = []
    monkeypatch.setattr(prompt, "ask_ocr", lambda *args: answers.append(False) or False)
    monkeypatch.setattr(cli, "process", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("OCR ran")))
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    assert cli.watch(tmp_path, 5, copy=True, notification=True) == 0
    assert answers == [False]
    assert not (tmp_path / "history.sqlite3").exists()


def test_watch_does_not_ocr_replaced_image(monkeypatch, tmp_path):
    from shotocr import cli

    first = Image.new("RGB", (10, 10), "white")
    replacement = Image.new("RGB", (10, 10), "black")
    clipboard = iter([first, replacement])
    monkeypatch.setattr(core, "clipboard_image", lambda: next(clipboard))
    monkeypatch.setattr(prompt, "ask_ocr", lambda *args: True)
    monkeypatch.setattr(cli, "process", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stale image OCR ran")))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt))
    assert cli.watch(tmp_path, 5, copy=True, notification=True) == 0

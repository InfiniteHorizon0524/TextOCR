# ShotOCR

本地运行的截图 OCR 命令行工具。读取剪贴板中的截图，使用 RapidOCR 和 ONNX Runtime 识别中英文，将文本写入 SQLite 历史，默认还会复制文本并发送桌面通知。识别本身无需云服务或 AI Agent。

## 安装

需要 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)。在本目录运行：

```powershell
uv venv .venv
uv sync --extra test
uv run shotocr --help
```

`uv sync` 创建和使用本目录的 `.venv`。默认模型和历史保存在本目录 `.local/models/`、`.local/history.sqlite3`；模型首次使用时由 RapidOCR 下载，之后可离线运行。也可通过 `--home` 指定其他目录。普通 wheel 安装时默认使用系统用户数据目录。

Linux 上 Pillow 读取图片剪贴板需要 `wl-paste`（Wayland，安装 `wl-clipboard`）或 `xclip`（X11）；Pyperclip 写入文本同样需要 `wl-clipboard`、`xclip` 或 `xsel`。桌面通知需要桌面会话和通知服务。macOS 通知还受系统通知权限和可执行文件签名限制。通知失败会提示警告，不影响 OCR 和历史保存。

## 使用

先使用系统截图快捷键让**图片**进入剪贴板，然后运行：

```powershell
uv run shotocr once
```

启动后台监听。命令返回后程序仍会运行，每 5 秒检查一次剪贴板。发现新图片时，屏幕右下角会弹出“是否需要 OCR”的窗口：选择“是”才会识别、保存历史、将文字复制回剪贴板并显示结果通知；选择“否”会跳过该图片：

```powershell
uv run shotocr start
uv run shotocr status
uv run shotocr stop
```

需要在终端前台运行时，使用 `uv run shotocr watch`，按 `Ctrl+C` 退出。`start` 和 `watch` 都可通过 `--interval` 修改检查间隔。如果弹窗期间剪贴板换成其他内容，旧弹窗会自动关闭；下一轮会询问新图片。弹窗打开时执行 `stop` 也会关闭弹窗。程序将新出现的剪贴板图片视为截图，无法从剪贴板内容可靠区分图片来源。后台日志保存在 `.local/worker.log`。默认不会随系统开机自动启动。Linux 需要安装系统的 Tk 支持包（通常名为 `python3-tk`）和图形桌面会话。

查看最近 20 条记录：

```powershell
uv run shotocr history
uv run shotocr history --limit 50
```

跳过复制或通知：`shotocr once --no-copy --no-notify`。数据目录参数要放在子命令之前，例如 `shotocr --home D:\OCRData once`。识别文本也会打印到标准输出，可重定向到文件。空图片或未识别出文字时不会保存记录。

可从其他项目以 `pip install .` 安装，再直接使用 `shotocr`。首次下载模型需要网络，完成后不依赖网络。SQLite 历史以明文存储识别内容，请自行管理 `.local` 目录。

## 开发与测试

```powershell
uv run pytest
```

模型下载与识别用 [RapidOCR](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/install/)；剪贴板图片读取用 [Pillow ImageGrab](https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html)。

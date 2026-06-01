# 源码安装与开发

> 本文档面向**开发者**或需要从源码运行的用户。普通用户请直接从
> [Releases](../../releases) 下载构建好的 `media-toolkit-gui-vX.Y.Z.exe`。

---

## 环境准备

本项目使用 [uv](https://github.com/astral-sh/uv) 管理 Python 与依赖。

```bash
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 安装

```bash
git clone https://github.com/<owner>/media-toolkit.git
cd media-toolkit

# 仅 CLI（最小依赖）
uv sync

# CLI + GUI
uv sync --extra gui

# 开发组（含 pytest / pyinstaller）
uv sync --extra gui --group dev
```

### 依赖

| 包 | 用途 | 何时安装 |
|---|---|---|
| `zhconv` | 译名繁体→简体转换 | CLI / GUI |
| `Pillow` | `manga make-cover` 图像处理 | CLI / GUI |
| `smartcrop` | `manga make-cover --smart` 显著性裁剪 | CLI / GUI |
| `PySide6` | 桌面 GUI 框架 | 仅 `--extra gui` |
| `pytest` | 单元测试 | 仅 `--group dev` |
| `pyinstaller` | 打包单文件 exe | 仅 `--group dev` |

> GUI 当前要求 Python 3.11 – 3.13（受 PySide6 wheel 覆盖范围限制）。
> 仅装 CLI 时无此限制。

---

## 运行

```bash
# 漫画工具
uv run manga-cli <subcommand> ...
uv run manga-gui

# 工件工具
uv run artifact-cli <subcommand> ...
uv run artifact-gui

# 双模块单窗口入口（推荐 GUI 用法）
uv run app-gui
```

### 体检

```bash
uv run manga-cli doctor
uv run artifact-cli doctor
```

打印当前 Python 版本与依赖安装状态；任一项异常时退出码 1，便于发 issue 前自查。

---

## 测试

```bash
uv run pytest
```

---

## 打包 exe（本地复现 CI）

CI 已经在 push tag 时自动跑 PyInstaller 并上传到 Release，本地仅当需要调试打包问题时才手动执行：

```bash
uv run pyinstaller --noconfirm --windowed --onefile \
  --name media-toolkit-gui \
  --add-data "module/manga/data/examples.json;module/manga/data" \
  --collect-submodules module \
  --collect-submodules base \
  --collect-submodules app \
  app/__main__.py
```

产物在 `dist/media-toolkit-gui.exe`。

---

## 发布

只需 push 一个 `vX.Y.Z` 形式的 tag，`.github/workflows/release.yml`
会自动跑 git-cliff 生成 changelog、PyInstaller 打包、创建 GitHub Release
并上传 exe。无需手动 `gh release create`。

```bash
git tag v0.3.1
git push origin v0.3.1
```

---

## 项目结构

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

# manga-toolkit

> 从网络下载的漫画文件，命名混乱、格式不一，时间一长就变得难以管理，几乎不可能直接导入 Booklore（现 Grimmory）。  
> 该项目旨在通过正则匹配批量规范文件名、填充标准元数据，并生成统一比例封面，让你的漫画收藏更加整洁、专业。

**如何快速判断该项目是否适合你？**

直接查看示例对比：  
[`mt/data/examples.json`](mt/data/examples.json)  
其中 `i`（input）为原始文件名，`e`（expected）为本项目处理后的预期结果。

---

漫画文件整理工具集，提供：

- 统一 CLI `manga-toolkit-cli`
- 可选桌面 GUI `manga-toolkit-gui`（PySide6）

含三个子命令：

| 子命令 | 功能 |
|---|---|
| `sourcefile` | 批量重命名源文件（.zip / .cbz），统一格式 |
| `metadata` | 向 CBZ 写入 ComicInfo.xml 元数据 |
| `cover` | 为 CBZ 写入 2:3 封面（源 `0001.*` → `0000.webp`；源 `cover.*` → `cover.webp`） |

---

## 安装

```bash
# 安装 uv（如尚未安装）
# Windows (PowerShell)：irm https://astral.sh/uv/install.ps1 | iex
# macOS / Linux：curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装项目（自动创建 .venv 并解析锁文件）
cd manga-toolkit
uv sync
```

### 依赖

| 包 | 用途 | 何时安装 |
|---|---|---|
| `zhconv` | 译名繁体→简体转换 | CLI / GUI |
| `Pillow` | `cover` 子命令图像解码 / 裁剪 / WebP 编码 | CLI / GUI |
| `smartcrop` | `cover --smart` 显著性裁剪 | CLI / GUI |
| `PySide6` | 桌面 GUI 框架 | 仅 `--extra gui` |

### 安装 GUI（可选）

```bash
uv sync --extra gui
uv run manga-toolkit-gui
```

> GUI 当前要求 Python 3.11 – 3.13（受 PySide6 wheel 覆盖范围限制）。
> 仅装 CLI 时无此限制。

### 体检

```bash
uv run manga-toolkit-cli doctor
```

打印当前 Python 版本与各依赖安装状态；任一项异常时退出码 1，便于发
issue 前自查或脚本判断。

---

## 目标命名格式

```
[作者] 漫画标题( VOL.XX)?
( CH.XX(-YY)?(+番外篇)? | 番外篇 | 后日谈 | 上篇 | 中篇 | 下篇)?
( ～话标题～)?( (系列))?( ¦译名¦)?
( [总集篇])?( [zh])?( [uncensored])?( [colorized])?( [ongoing])?
```

### 分编词规则

| 类别 | 词汇 | 输出位置 | 与 CH. 的关系 |
|---|---|---|---|
| 合集类 | `总集篇` | `[总集篇]` tag（与 `[zh]` 同位，在其前） | — |
| 附录类 | `番外篇` / `后日谈` | CH. **位置** | **互斥**（二选一）|
| 结构类 | `上篇` / `中篇` / `下篇` | CH. **位置** | **互斥**（二选一）|

---

## sourcefile 子命令

```bash
# 循环拖入模式（推荐日常使用，默认不移动）
manga-toolkit-cli sourcefile --drag

# 拖入后自动移动到整理目录（仅当显式指定 --move-to 时启用移动）
manga-toolkit-cli sourcefile --drag --move-to /path/to/sorted

# 批量预览（不修改文件）
manga-toolkit-cli sourcefile --root /path/to/manga

# 批量执行
manga-toolkit-cli sourcefile --root /path/to/manga --apply

# 列出 / 回退已有的 session 记录（当前 apply 不再写新 session）
manga-toolkit-cli sourcefile --list-sessions
manga-toolkit-cli sourcefile --rollback

# 内置解析示例（回归测试）
manga-toolkit-cli sourcefile --examples

# 启用调试输出（放在子命令之前）
manga-toolkit-cli --debug sourcefile --drag

# 并行 plan（纯字符串处理为主，收益有限；主要用于大目录的进度反馈）
manga-toolkit-cli sourcefile --root /path/to/manga --jobs 4
```

---

## metadata 子命令

生成 ComicInfo v2.1 XML，写入 CBZ 文件。

```bash
# 预览（不修改文件）
manga-toolkit-cli metadata --root /path/to/cbz

# 实际写入
manga-toolkit-cli metadata --root /path/to/cbz --apply

# 循环拖入模式
manga-toolkit-cli metadata --drag --move-to /path/to/sorted

# 内置示例
manga-toolkit-cli metadata --examples

# 并行 plan（plan 阶段是 IO 密集 ZIP 扫描；大目录可加速）
manga-toolkit-cli metadata --root /path/to/cbz --apply --jobs 4
```

### 字段映射与顺序

ComicInfo.xml 中字段输出顺序：

```
Publisher → Writer → Title → Volume → Number → Series → Format →
LanguageISO → Genre → Tags → PageCount → Notes
```

| ComicInfo 字段 | 来源 |
|---|---|
| `Publisher` | 同目录 `[社团]：XX.txt` 文件名 |
| `Writer` | 文件名中的 `[作者]` |
| `Title` | 文件名（去除标签括号） |
| `Volume` | `VOL.XX` |
| `Number` | `CH.XX` 数字部分，**或** 独立分编词（番外篇 / 后日谈 / …） |
| `Series` | `(系列名)` |
| `Format` | 合集类分编词（`总集篇`）；其它情况留空 |
| `LanguageISO` | `[zh]` / `[ja]` / `[ko]` / `[en]` / `[zxx]` |
| `Genre` | uncensored / colorized / ongoing |
| `Tags` | 保留 CBZ 内已有值（不覆盖） |
| `PageCount` | 压缩包内图片文件数（jpg / jpeg / png / bmp / gif / psd / webp / avif / jxl） |
| `Notes` | `"metadata creator": "manga-toolkit-cli 0.1.0"` |

---

## cover 子命令

为 CBZ 写入一张 2:3 / ≤ 1000×1500 的 WebP 封面。目标文件名取决于源图：

| 源图 | 目标 | 行为 |
|---|---|---|
| `0001.*` | `0000.webp` | 追加新封面，按字典序排在所有页面之前 |
| `cover.*` | `cover.webp` | 替换原 `cover.*`（同 stem 任何扩展名都会被清理） |

**背景**：[grimmory](https://github.com/grimmory-tools/grimmory) 在生成 cover 时若源图超过 2000 万像素会拒绝处理：

```
Rejected image: dimensions 4000x5400 (21600000 pixels) exceed limit 20000000 — possible decompression bomb
```

本子命令产出的 WebP 严格命中 1000×1500（与 grimmory 内部 cover 目标尺寸 2:3 对齐），并以追加方式写入原 CBZ，不重建压缩包。源图小于 1000×1500 时保持原尺寸（不放大）。

```bash
# 预览
manga-toolkit-cli cover --root /path/to/cbz

# 实际写入
manga-toolkit-cli cover --root /path/to/cbz --apply

# smartcrop 显著性裁剪（横图保留主体更稳）
manga-toolkit-cli cover --root /path/to/cbz --apply --smart

# 并行处理（plan 阶段；4 个文件以上才会真正启用）
manga-toolkit-cli cover --root /path/to/cbz --apply --jobs 4
manga-toolkit-cli cover --root /path/to/cbz --apply --jobs 0   # 自动 min(cpu, 4)

# 循环拖入
manga-toolkit-cli cover --drag --move-to /path/to/sorted
```

每处理一个 cbz 即打印进度行 `✅ [12/345] 文件名`，便于大批量任务跟踪。
plan 阶段是 CPU 密集的解码+裁剪+编码，apply 阶段（ZIP 追加）已经很快不并行。

### 行为约定

| 项 | 值 |
|---|---|
| 写入文件名 | 源 `0001.*` → `0000.webp`；源 `cover.*` → `cover.webp` |
| 源图查找 | ZIP 根目录按优先级 `cover.*` → `0001.*`（不递归子目录） |
| 输出比例 | 2:3（宽:高） |
| 输出尺寸 | 1000×1500（源更小则保留原尺寸，不放大） |
| 写入方式 | ZIP 追加；同 stem 的旧条目（任何扩展名）成为死空间，与 ComicInfo.xml 同策略 |
| 处理范围 | `--root` 下所有 .cbz（递归子目录） |

### 裁剪模式

| 模式 | 触发 | 说明 |
|---|---|---|
| `center`（默认） | 不加 `--smart` | 居中裁剪到 2:3，最简单、可预测；横图（如跨页扉页）可能丢主体 |
| `smart` | `--smart` | smartcrop 基于边缘 / 饱和度 / 肤色综合打分挑选最佳子矩形 |

---

## GUI（PySide6）

```bash
uv sync --extra gui
uv run manga-toolkit-gui
```

主窗口为「上方三个子命令 Tab + 下方共享日志面板」。每个 Tab 流程一致：

1. 选择 / 拖入根目录（可选填「处理后移动到」）
2. 调整选项（如 cover 的 `smart` / `quality`，所有子命令的 `jobs`）
3. 点「扫描预览」→ 后台跑 plan，预览渲染到日志面板
4. 确认无误后点「执行」→ QMessageBox 二次确认 → 后台跑 apply → 可选移动

GUI 完全复用 `mt.workflow.{sourcefile,metadata,cover}` 的 `plan_*` / `apply_*`
函数，通过 `mt.infra.console.set_output()` 接管文本输出到日志框，与 CLI 共用
所有渲染逻辑（`mt.presentation.view`）。

---

## 项目结构

```
mt/
├── __init__.py
├── __main__.py                  — 适配 `python -m mt` 的转发层
├── manga_toolkit_cli.py         — 统一 CLI 实现（sourcefile + metadata 子命令）
├── cli/                         — 子命令调度层
│   ├── sourcefile.py            — sourcefile 子命令
│   ├── metadata.py              — metadata 子命令
│   ├── cover.py                 — cover 子命令
│   └── examples.py              — 内置示例（sourcefile / metadata 共用）
├── gui/                         — 桌面 GUI（PySide6，可选依赖）
│   ├── app.py                   — QApplication 入口（manga-toolkit-gui）
│   ├── main_window.py           — Tab + 共享 LogView
│   ├── qt_sink.py               — 接管 console.emit 到 Qt 信号
│   ├── tabs/                    — 三个子命令各自 Tab
│   ├── workers/                 — QThread 阻塞任务包装
│   └── widgets/                 — LogView / PathPicker
├── core/                        — 纯数据层（无 I/O，无内部依赖）
│   ├── config.py                — 全局默认配置
│   ├── models.py                — Chapter / Volume / MangaInfo
│   │                              / SourcefilePlan / MetadataPlan / CoverPlan
│   └── patterns.py              — 正则表达式常量与规则表
├── infra/                       — 基础设施层（终端、I/O、字符串工具、调度）
│   ├── utils.py                 — 纯工具函数（繁简、路径、重命名）
│   ├── console.py               — 终端输出 & 日志
│   └── parallel.py              — 通用 plan 调度: run_plans (进度行 + 可选并行)
├── naming/                      — 名称解析与构建
│   ├── parser.py                — parse_name(author, name) → MangaInfo
│   └── builder.py               — build_new_name(info) → str
├── presentation/                — 领域对象的终端渲染
│   └── view.py                  — print_run_banner / print_*_preview / print_metadata_diff_table
└── workflow/                    — 高层工作流
    ├── sourcefile.py            — 源文件扫描、重命名执行
    ├── metadata.py              — ComicInfo.xml 生成 & 写入
    ├── cover.py                 — 封面查找、裁剪、WebP 编码、CBZ 追加写入
    ├── drag.py                  — 通用拖入循环 + 目录搬移（共用）
    └── session.py               — 操作记录 & 回退（仅 sourcefile 读取使用）
```

> 命名约定：Python 模块名遵循 PEP 8（小写 + 下划线），暴露的 CLI 命令名遵循 Unix 惯例（小写 + 连字符）。
> `pyproject.toml` 中 `manga-toolkit-cli = "mt.manga_toolkit_cli:main"` 即为两者的桥接。

依赖关系（低层 → 高层）：

```
core/config · core/models
        ↓
core/patterns      ← core/models
        ↓
infra/utils        ← core/patterns
infra/console      ← core/models
infra/parallel     ← infra/console
        ↓
naming/parser      ← core/models · core/patterns · infra/utils · infra/console
naming/builder     ← core/models · core/patterns · infra/utils
        ↓
workflow/drag      ← infra/utils · infra/console
workflow/session   ← core/models · core/config · infra/utils · infra/console
workflow/sourcefile← core/models · core/config · naming/* · infra/{utils,console,parallel} · presentation · workflow/drag
workflow/metadata  ← core/models · core/config · core/patterns · infra/{console,parallel} · naming/parser · presentation · workflow/drag
workflow/cover     ← core/models · core/config · infra/{console,parallel} · presentation · workflow/drag
        ↓
mt/cli/{sourcefile,metadata,cover,examples}
        ↓
mt/manga_toolkit_cli.py
```

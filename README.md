# media-toolkit

> 媒体文件整理工具集，含两个业务包：
>
> - **mt**（漫画工具）：批量规范文件名、写 ComicInfo.xml、生成统一比例封面、序号化打包 STORED zip。  
>   入口：CLI `mt-cli` / GUI `mt-gui`（PySide6）。
> - **ft**（文件工具）：把拖入的文件/文件夹按"作者名"自动归类到预设工作目录（支持别名）。  
>   入口：CLI `ft-cli classify` / GUI `ft-gui`；首次启动需按 `ft/config_template.json` 创建本地配置。
>
> 双模块单窗口入口：`app-gui`（同窗口装载 mt + ft 两个 module）。

**如何快速判断 mt 是否适合你？**

直接查看示例对比：  
[`mt/data/examples.json`](mt/data/examples.json)  
其中 `i`（input）为原始文件名，`e`（expected）为本项目处理后的预期结果。

下文按 mt 子命令分节描述漫画整理；ft 业务文档见 `ft/`（待补充）。

---

mt 含四个子命令：

| 子命令 | 功能 |
|---|---|
| `pack` | 图片目录序号化重命名 + STORED zip 打包 |
| `sourcefile` | 批量重命名源文件（.zip / .cbz），统一格式 |
| `cover` | 为 CBZ 写入 2:3 封面（源 `0001.*` → `0000.webp`；源 `cover.*` → `cover.webp`） |
| `metadata` | 向 CBZ 写入 ComicInfo.xml 元数据 |

---

## 安装

```bash
# 安装 uv（如尚未安装）
# Windows (PowerShell)：irm https://astral.sh/uv/install.ps1 | iex
# macOS / Linux：curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装项目（自动创建 .venv 并解析锁文件）
cd media-toolkit
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
uv run mt-gui
```

> GUI 当前要求 Python 3.11 – 3.13（受 PySide6 wheel 覆盖范围限制）。
> 仅装 CLI 时无此限制。

### 体检

```bash
uv run mt-cli doctor
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

## pack 子命令

递归识别图片目录「打包单位」，将图片按序号规则重命名后以 ZIP_STORED（不压缩）打包为同级 `<dir>.zip`，完成后删除源目录。

### 打包单位识别

| 类型 | 识别条件 | zip 内结构 |
|---|---|---|
| `flat` | 目录内仅图片，无子目录，且图片数 ≥ 最小阈值 | 图片直接置 zip 根目录 |
| `nested` | 目录内仅子目录，每个子目录为纯图片叶 | 保留子目录名作路径前缀；顶层 `cover.*` / `0000.*` / `ComicInfo.xml` 原名写入 zip 根 |

混合目录（图+子目录同层，且顶层图非 cover/0000 类）跳过；图片数不足的目录跳过；容器层（子目录不全是图片叶）自动下钻。

### 序号规则

每个目录独立计数，从 `0001` 起步，4 位零填充（图片数 ≥ 10000 时自动扩位），扩展名保留原扩展名并小写。

```bash
# 批量预览（不修改文件）
mt-cli pack --root /path/to/albums

# 批量执行（重命名 + 打包 + 删除源目录）
mt-cli pack --root /path/to/albums --apply

# 并行 plan（plan 阶段；≥ 4 个单位时才真正启用）
mt-cli pack --root /path/to/albums --apply --jobs 4
mt-cli pack --root /path/to/albums --apply --jobs 0   # 自动 min(cpu, 4)
```

---

## sourcefile 子命令

```bash
# 批量预览（不修改文件）
mt-cli sourcefile --root /path/to/manga

# 批量执行
mt-cli sourcefile --root /path/to/manga --apply

# 内置解析示例（回归测试）
mt-cli sourcefile --examples

# 并行 plan（纯字符串处理为主，收益有限；主要用于大目录的进度反馈）
mt-cli sourcefile --root /path/to/manga --jobs 4
```

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
mt-cli cover --root /path/to/cbz

# 实际写入
mt-cli cover --root /path/to/cbz --apply

# smartcrop 显著性裁剪（横图保留主体更稳）
mt-cli cover --root /path/to/cbz --apply --smart

# 并行处理（plan 阶段；4 个文件以上才会真正启用）
mt-cli cover --root /path/to/cbz --apply --jobs 4
mt-cli cover --root /path/to/cbz --apply --jobs 0   # 自动 min(cpu, 4)
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

## metadata 子命令

生成 ComicInfo v2.1 XML，写入 CBZ 文件。

```bash
# 预览（不修改文件）
mt-cli metadata --root /path/to/cbz

# 实际写入
mt-cli metadata --root /path/to/cbz --apply

# 内置示例
mt-cli metadata --examples

# 并行 plan（plan 阶段是 IO 密集 ZIP 扫描；大目录可加速）
mt-cli metadata --root /path/to/cbz --apply --jobs 4
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
| `Notes` | `"metadata creator": "mt-cli 0.1.0"` |

---

## GUI（PySide6）

```bash
uv sync --extra gui
uv run mt-gui
```

主窗口为「上方三个子命令 Tab + 下方共享日志面板」。每个 Tab 流程一致：

1. 选择 / 拖入根目录（可选填「处理后移动到」）
2. 调整选项（如 cover 的 `smart` / `quality`，所有子命令的 `jobs`）
3. 点「扫描预览」→ 后台跑 plan，预览渲染到日志面板
4. 确认无误后点「执行」→ QMessageBox 二次确认 → 后台跑 apply → 可选移动

GUI 完全复用 `mt.workflow.{sourcefile,metadata,cover}` 的 `plan_*` / `apply_*`
函数，通过 `base.console.set_output()` 接管文本输出到日志框，与 CLI 共用
所有渲染逻辑（`mt.presentation.view`）。

---

## 项目结构

```
base/                            — 跨业务共享基础设施
├── console.py                   — 终端输出 & GUI sink 路由（emit / warn / error / set_output）
├── drag_loop.py                 — 通用拖入循环（run_drag_loop）
├── fs.py                        — 文件系统工具（merge_into / move_dir / safe_rmtree）
└── gui/                         — 共享 GUI 组件（PySide6，可选）
    ├── shell.py                 — Shell(QMainWindow)：左侧 Tab 宿主，register_module()
    ├── app_check.py             — check_pyside6()：启动前依赖检查
    ├── log_view.py              — LogView：日志滚动文本框
    ├── qt_sink.py               — QtSink：console → LogView 桥接
    ├── path_picker.py           — PathPicker：路径选择 + 拖入 widget
    ├── worker.py                — BaseWorker(QThread)：通用后台任务
    └── config.py                — QSettings 辅助（窗口几何持久化）

mt/                              — 漫画工具（manga toolkit）
├── __init__.py                  — 版本号（__version__）
├── __main__.py                  — 适配 `python -m mt` 的转发层
├── cli/                         — CLI 入口 + 子命令调度（main = mt-cli）
│   ├── __init__.py              — build_parser() / main()
│   ├── sourcefile.py            — sourcefile 子命令
│   ├── metadata.py              — metadata 子命令
│   ├── cover.py                 — cover 子命令
│   ├── pack.py                  — pack 子命令
│   ├── doctor.py                — doctor 子命令（环境体检）
│   └── examples.py              — 内置示例（sourcefile / metadata 共用）
├── gui/                         — 桌面 GUI（PySide6，可选依赖）
│   ├── __init__.py              — QApplication 入口（main = mt-gui）
│   ├── __main__.py              — `python -m mt.gui` / PyInstaller 入口
│   ├── module.py                — MangaModule（被 Shell 装载）
│   ├── tabs/                    — 四个子命令各自 Tab
│   └── workers/                 — QThread 阻塞任务包装
├── core/                        — 纯数据层（无 I/O，无内部依赖）
│   ├── config.py                — 全局默认配置
│   ├── models.py                — Chapter / Volume / MangaInfo / *Plan 数据类
│   └── patterns.py              — 正则表达式常量与规则表
├── infra/                       — 基础设施层（字符串工具、调度）
│   ├── utils.py                 — 纯工具函数（繁简转换、路径、重命名）
│   └── parallel.py              — run_plans：进度行 + 可选并行
├── naming/                      — 名称解析与构建
│   ├── parser.py                — parse_name(author, name) → MangaInfo
│   └── builder.py               — build_new_name(info) → str
├── presentation/                — 领域对象的终端渲染
│   └── view.py                  — print_run_banner / print_*_preview / print_metadata_diff_table
└── workflow/                    — 高层工作流
    ├── sourcefile.py            — 源文件扫描、重命名执行
    ├── metadata.py              — ComicInfo.xml 生成 & 写入
    ├── cover.py                 — 封面查找、裁剪、WebP 编码、CBZ 追加写入
    ├── pack.py                  — 图片目录序号化 + STORED zip 打包
    └── session.py               — 操作记录 & 回退（仅 sourcefile 使用）

ft/                              — 文件工具（file toolkit）
├── __init__.py
├── cli/                         — CLI 入口（main = ft-cli）
│   ├── __init__.py              — build_parser() / main()
│   └── classify.py              — classify 子命令
├── gui/                         — 桌面 GUI（PySide6，可选依赖）
│   ├── __init__.py              — QApplication 入口（main = ft-gui）
│   ├── module.py                — FtModule（被 Shell 装载）
│   ├── tabs/classify_tab.py     — ClassifyTab：拖入区 + 工作目录面板
│   └── widgets/                 — drop_area / candidate_dialog
├── workflow/classify/           — 归类工作流
│   ├── config.py                — WorkDir / Config / load_config()
│   ├── path.py                  — path_to_author_name()
│   ├── alias.py                 — scan_aliases()（扫描 [别名]：XX.txt）
│   ├── matcher.py               — find_candidates()
│   └── ops.py                   — classify_one()
└── config_template.json         — 配置模板（首次使用时参照创建 config.json）

app/                             — 顶层双模块启动器
└── gui.py                       — main = app-gui（同窗口装载 mt + ft）
```

> 命名约定：Python 模块名遵循 PEP 8（小写 + 下划线），暴露的 CLI 命令名遵循 Unix 惯例（小写 + 连字符）。
> `pyproject.toml` 中 `mt-cli = "mt.cli:main"` 即为两者的桥接。

依赖关系（低层 → 高层）：

```
base/console · base/fs · base/drag_loop
        ↓
mt/core/{config,models,patterns}
        ↓
mt/infra/{utils,parallel}    ← base/console
        ↓
mt/naming/{parser,builder}   ← mt/core · mt/infra · base/console
        ↓
mt/workflow/*                ← mt/core · mt/infra · mt/naming · mt/presentation · base/*
        ↓
mt/cli/__init__.py  (main → mt-cli)

ft/workflow/classify/*       ← base/{console,fs,drag_loop}
        ↓
ft/cli/__init__.py  (main → ft-cli)

base/gui/{shell,worker,…}   ← base/console
mt/gui/module.py             ← mt/workflow/* · base/gui
ft/gui/module.py             ← ft/workflow/* · base/gui
        ↓
app/gui.py  (main → app-gui)  ← mt/gui · ft/gui · base/gui
```

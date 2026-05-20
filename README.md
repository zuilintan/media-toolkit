# manga-toolkit

漫画文件整理工具集，提供统一 CLI `manga-toolkit-cli`，含两个子命令：

| 子命令 | 功能 |
|---|---|
| `rename` | 批量重命名漫画文件 / 目录，统一格式 |
| `comicinfo` | 向 CBZ 写入 ComicInfo.xml 元数据 |

---

## 安装

```bash
# 安装 poetry（如尚未安装）
pip install poetry

# 安装项目（含可选繁简转换）
cd manga-toolkit
poetry install -E zhconv
```

### 可选依赖

| 包 | 用途 | 安装方式 |
|---|---|---|
| `zhconv` | 译名繁体→简体转换 | `poetry install -E zhconv` |

---

## 目标命名格式

```
[作者] 漫画标题( 总集篇)?( VOL.XX)?
( CH.XX(-YY)?(+番外篇)? | 番外篇 | 后日谈 | 上篇 | 中篇 | 下篇)?
( ～话标题～)?( (系列))?( ¦译名¦)?
( [zh])?( [uncensored])?( [colorized])?( [ongoing])?
```

### 附录词规则

| 词汇 | 所在位置 | 与 CH. 的关系 |
|---|---|---|
| `总集篇` | VOL. **之前** | — |
| `番外篇` / `后日谈` / `上篇` / `中篇` / `下篇` | VOL. **之后**，CH. **位置** | **互斥**（二选一）|

---

## rename 子命令

```bash
# 循环拖入模式（推荐日常使用，默认不移动）
manga-toolkit-cli rename --drag

# 拖入后自动移动到整理目录（仅当显式指定 --target 时启用移动）
manga-toolkit-cli rename --drag --target /path/to/sorted

# 批量预览（不修改文件）
manga-toolkit-cli rename --root /path/to/manga

# 批量执行
manga-toolkit-cli rename --root /path/to/manga --apply

# 回退上次操作
manga-toolkit-cli rename --rollback

# 列出所有操作记录
manga-toolkit-cli rename --list-sessions

# 内置解析示例（回归测试）
manga-toolkit-cli rename --examples

# 启用调试输出（放在子命令之前）
manga-toolkit-cli --debug rename --drag
```

---

## comicinfo 子命令

生成 ComicInfo v2.1 XML，写入 CBZ 文件。

```bash
# 预览（不修改文件）
manga-toolkit-cli comicinfo --root /path/to/cbz

# 实际写入
manga-toolkit-cli comicinfo --root /path/to/cbz --apply

# 内置示例
manga-toolkit-cli comicinfo --examples
```

### 字段映射与顺序

ComicInfo.xml 中字段输出顺序：

```
Publisher → Writer → Title → Volume → Number → Series →
LanguageISO → Genre → PageCount → Tags → Notes
```

| ComicInfo 字段 | 来源 |
|---|---|
| `Publisher` | 同目录 `[社团]：XX.txt` 文件名 |
| `Writer` | 文件名中的 `[作者]` |
| `Title` | 文件名（去除标签括号） |
| `Volume` | `VOL.XX` |
| `Number` | `CH.XX` 数字部分，**或** 独立附录词（番外篇 / 后日谈 / …） |
| `Series` | `(系列名)` |
| `LanguageISO` | `[zh]` / `[ja]` / `[ko]` / `[en]` / `[zxx]` |
| `Genre` | uncensored / colorized / ongoing |
| `PageCount` | 压缩包内图片文件数（jpg / jpeg / png / bmp / gif / psd / webp / avif / jxl） |
| `Tags` | 保留 CBZ 内已有值（不覆盖） |
| `Notes` | `"metadata creator": "manga-toolkit-cli 0.1.0"` |

---

## 项目结构

```
mt/
├── __init__.py
├── __main__.py                  — 适配 `python -m mt` 的转发层
├── manga_toolkit_cli.py         — 统一 CLI 实现（rename + comicinfo 子命令）
├── core/                        — 纯数据层（无 I/O，无内部依赖）
│   ├── __init__.py
│   ├── config.py                — 全局默认配置
│   ├── models.py                — Chapter / Volume / MangaInfo / RenamePlan
│   └── patterns.py              — 正则表达式常量与规则表
├── infra/                       — 基础设施层（终端、I/O、字符串工具）
│   ├── __init__.py
│   ├── utils.py                 — 纯工具函数（繁简、路径、重命名）
│   └── console.py               — 终端输出 & 日志
├── naming/                      — 名称解析与构建
│   ├── __init__.py
│   ├── parser.py                — parse_name(author, name) → MangaInfo
│   └── builder.py               — build_new_name(info) → str
└── workflow/                    — 高层工作流
    ├── __init__.py
    ├── scanner.py               — 目录扫描、重命名执行、拖入模式
    ├── session.py               — 操作记录 & 回退
    └── comicinfo.py             — ComicInfo.xml 生成 & 写入
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
        ↓
naming/parser      ← core/models · core/patterns · infra/utils · infra/console
naming/builder     ← core/models · core/patterns · infra/utils
        ↓
workflow/session   ← core/models · core/config · infra/utils · infra/console
workflow/scanner   ← core/models · core/config · naming/* · infra/* · workflow/session
workflow/comicinfo ← core/models · core/config · core/patterns · infra/console · naming/parser
        ↓
mt/manga_toolkit_cli.py
```

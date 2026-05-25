# manga-toolkit

漫画文件整理工具集，提供统一 CLI `manga-toolkit-cli`，含两个子命令：

| 子命令 | 功能 |
|---|---|
| `sourcefile` | 批量重命名源文件（.zip / .cbz），统一格式 |
| `metadata` | 向 CBZ 写入 ComicInfo.xml 元数据 |

---

## 安装

```bash
# 安装 poetry（如尚未安装）
pip install poetry

# 安装项目
cd manga-toolkit
poetry install
```

### 依赖

| 包 | 用途 |
|---|---|
| `zhconv` | 译名繁体→简体转换（必选） |

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

## 项目结构

```
mt/
├── __init__.py
├── __main__.py                  — 适配 `python -m mt` 的转发层
├── manga_toolkit_cli.py         — 统一 CLI 实现（sourcefile + metadata 子命令）
├── cli/                         — 子命令调度层
│   ├── sourcefile.py            — sourcefile 子命令
│   ├── metadata.py              — metadata 子命令
│   └── examples.py              — 内置示例（双子命令共用）
├── core/                        — 纯数据层（无 I/O，无内部依赖）
│   ├── config.py                — 全局默认配置
│   ├── models.py                — Chapter / Volume / MangaInfo
│   │                              / SourcefilePlan / MetadataPlan
│   └── patterns.py              — 正则表达式常量与规则表
├── infra/                       — 基础设施层（终端、I/O、字符串工具）
│   ├── utils.py                 — 纯工具函数（繁简、路径、重命名）
│   └── console.py               — 终端输出 & 日志
├── naming/                      — 名称解析与构建
│   ├── parser.py                — parse_name(author, name) → MangaInfo
│   └── builder.py               — build_new_name(info) → str
├── presentation/                — 领域对象的终端渲染
│   └── view.py                  — print_run_banner / print_*_preview / print_metadata_fields
└── workflow/                    — 高层工作流
    ├── sourcefile.py            — 源文件扫描、重命名执行
    ├── metadata.py              — ComicInfo.xml 生成 & 写入
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
        ↓
naming/parser      ← core/models · core/patterns · infra/utils · infra/console
naming/builder     ← core/models · core/patterns · infra/utils
        ↓
workflow/drag      ← infra/utils · infra/console
workflow/session   ← core/models · core/config · infra/utils · infra/console
workflow/sourcefile← core/models · core/config · naming/* · infra/* · presentation · workflow/drag
workflow/metadata  ← core/models · core/config · core/patterns · infra/console · naming/parser · presentation · workflow/drag
        ↓
mt/cli/{sourcefile,metadata,examples}
        ↓
mt/manga_toolkit_cli.py
```

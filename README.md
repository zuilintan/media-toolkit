# manga-toolkit

漫画文件整理工具集，包含两个 CLI 工具：

| 命令 | 功能 |
|---|---|
| `manga-rename` | 批量重命名漫画文件/目录，统一格式 |
| `manga-comicinfo` | 向 CBZ 写入 ComicInfo.xml 元数据 |

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

## manga-rename

```bash
# 循环拖入模式（推荐日常使用）
manga-rename --drag

# 拖入后自动移动到整理目录
manga-rename --drag --target /path/to/sorted

# 批量预览（不修改文件）
manga-rename --root /path/to/manga

# 批量执行
manga-rename --root /path/to/manga --apply

# 回退上次操作
manga-rename --rollback

# 列出所有操作记录
manga-rename --list-sessions

# 内置解析示例（回归测试）
manga-rename --examples

# 启用调试输出
manga-rename --drag --debug
```

---

## manga-comicinfo

生成 ComicInfo v2.1 XML，写入 CBZ 文件。

```bash
# 预览（不修改文件）
manga-comicinfo --root /path/to/cbz

# 实际写入
manga-comicinfo --root /path/to/cbz --apply

# 内置示例
manga-comicinfo --examples
```

### 字段映射

| ComicInfo 字段 | 来源 |
|---|---|
| `Publisher` | 同目录 `[社团]：XX.txt` 文件名 |
| `Writer` | 文件名中的 `[作者]` |
| `Title` | 文件名（去除标签括号） |
| `Volume` | `VOL.XX` |
| `Number` | `CH.XX` 数字部分，**或** 独立附录词（番外篇/后日谈/…） |
| `Series` | `(系列名)` |
| `Genre` | uncensored / colorized / ongoing |
| `LanguageISO` | `[zh]` / `[ja]` / `[ko]` / `[en]` / `[zxx]` |
| `Tags` | 保留 CBZ 内已有值（不覆盖） |

---

## 项目结构

```
mt/
├── __init__.py
├── config.py          — 全局默认配置
├── models.py          — 数据模型（Chapter / Volume / MangaInfo / RenamePlan）
├── patterns.py        — 正则表达式常量
├── utils.py           — 纯工具函数（无 I/O）
├── console.py         — 终端输出 & 日志
├── parser.py          — 文件名解析（parse_name）
├── builder.py         — 新文件名构建（build_new_name）
├── scanner.py         — 目录扫描、重命名执行、拖入模式
├── session.py         — 操作记录 & 回退
├── comicinfo.py       — ComicInfo.xml 生成 & 写入
└── cli/
    ├── rename_cmd.py  — manga-rename 入口
    └── comicinfo_cmd.py — manga-comicinfo 入口
```

依赖关系（低层 → 高层）：

```
models / config
    ↓
patterns
    ↓
utils ← patterns
    ↓
console ← models
    ↓
parser ← models, patterns, utils, console
builder ← models, patterns, utils
    ↓
scanner ← parser, builder, utils, console, session
session ← models, utils, console, config
comicinfo ← models, patterns, config, parser, console
    ↓
cli/rename_cmd.py
cli/comicinfo_cmd.py
```

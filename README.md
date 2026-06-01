# media-toolkit

> 媒体文件整理工具集，单窗口 GUI 装载两个相互独立的业务模块：
>
> - **artifact**（工件工具）：拖入文件/文件夹按"作者名"自动归类到预设工作目录，支持别名映射。
> - **manga**（漫画工具）：批量规范文件名、写 ComicInfo.xml、生成统一比例封面、序号化打包 STORED zip。

---

## 安装

从 [Releases](../../releases) 页面下载最新 `media-toolkit-gui-vX.Y.Z.exe`，双击运行即可，免安装、单文件。

> 仅 Windows 提供 exe 构建。其它平台或希望从源码运行，见 [DEVELOPMENT.md](DEVELOPMENT.md)。

启动后窗口左侧为两个模块切换（**manga** / **artifact**），各自包含若干业务子 Tab。

---

## artifact ─ 文件归类

把拖入的文件 / 文件夹按"作者名"自动归类到预设工作目录里对应的作者子文件夹。
适合**多个网络盘 / 多个工作目录**并存、人工分类成本高的场景。

### 工作流程

1. 拖入路径 → 自动取末段目录名作为「作者名」（拖文件则取父目录名）
2. 在所有 WorkDir 内查找候选作者目录：
   - **精确匹配**：`<WorkDir>/<作者名>` 已存在
   - **别名匹配**：扫描各 WorkDir 中以 `[别名]：xxx.txt`（全角冒号 U+FF1A）命名的空文件，命中 `xxx == 作者名` 时映射到该文件所在的作者目录
3. 候选 0 / 1 / N 分支：
   - **0 个** → 列出全部 WorkDir 让你选一个，目标 = `<选中 WorkDir>/<作者名>`（自动创建）
   - **1 个** → 直接使用
   - **N 个** → 弹候选列表选择
4. 搬移：目录用合并策略递归移动并清空源；同名文件已存在则跳过单个文件
5. 完成后自动用资源管理器打开目标目录；若 WorkDir 配置了 `search_url_template`，同时打印搜索 URL

### 首次配置

首启时会在 `<user_config>/media-toolkit/config/artifact.json` 落盘空配置。
在 GUI 中点：

- **📝 修改配置** — 用系统关联程序打开 `artifact.json`
- **🔁 重载配置** — 修改保存后点此重新读取 workdirs
- **🔄 刷新别名** — 重新扫描各 WorkDir 中的 `[别名]：*.txt`

配置示例（`artifact.workdirs` 数组中每项一个工作目录）：

```json
{
  "artifact.workdirs": [
    {
      "path": "M:/MMD/作者",
      "search_url_template": "https://www.xxx.xxx/search?type=video&query={author}"
    },
    {
      "path": "M:/Gallery/作者",
      "search_url_template": ""
    }
  ]
}
```

`search_url_template` 中的 `{author}` 占位符会被 URL-encode 后的作者名替换；留空表示完成后不打印 URL。

### 别名机制

在某个作者目录下放一个**空文件**：

```
M:/MMD/作者/AuthorA/[别名]：alias-name.txt
```

之后拖入名为 `alias-name` 的文件夹也会被识别为 AuthorA。别名匹配大小写不敏感，扫描结果会落盘到本地缓存，下次启动直接复用，无需重新跨网络盘扫描。

### CLI

```bash
artifact-cli classify --drag                       # 循环拖入模式（推荐）
artifact-cli classify ./AuthorA                    # 单次处理
artifact-cli classify ./a ./b ./c                  # 多个一起处理
artifact-cli classify ./a --target M:/MMD/作者/A    # 直接指定目标，跳过候选交互
artifact-cli classify --drag --no-open             # 完成后不开资源管理器
```

---

## manga ─ 漫画整理

含四个子命令，覆盖从图片打包到元数据写入的完整链路：

| 子命令 | 功能 |
|---|---|
| `pack-pic` | 图片目录序号化重命名 + STORED zip 打包 |
| `std-title` | 批量重命名源文件（.zip / .cbz），统一格式 |
| `make-cover` | 为 CBZ 写入 2:3 封面（源 `0001.*` 或 `cover.*` → `0000.webp`） |
| `make-meta` | 向 CBZ 写入 ComicInfo.xml 元数据 |

GUI 主窗口的 manga 模块对应「打包 / 命名 / 封面 / 元数据」四个子 Tab，每个 Tab 都是
"选根目录 → 调整选项 → 预览 → 二次确认 → 执行"的流程，与 CLI 共用所有渲染逻辑。

样例对比可看 [`module/manga/data/examples.json`](module/manga/data/examples.json)
（`i` 为原始文件名，`e` 为处理后预期结果）。

### 目标命名格式

```
[作者] 漫画标题( VOL.XX)?
( CH.XX(-YY)?(+番外篇)? | 番外篇 | 后日谈 | 上篇 | 中篇 | 下篇)?
( ～话标题～)?( (系列))?( ¦译名¦)?
( [总集篇])?( [zh])?( [uncensored])?( [colorized])?( [ongoing])?
```

#### 分编词规则

| 类别 | 词汇 | 输出位置 | 与 CH. 的关系 |
|---|---|---|---|
| 合集类 | `总集篇` | `[总集篇]` tag（与 `[zh]` 同位，在其前） | — |
| 附录类 | `番外篇` / `后日谈` | CH. **位置** | **互斥**（二选一）|
| 结构类 | `上篇` / `中篇` / `下篇` | CH. **位置** | **互斥**（二选一）|

### pack-pic 子命令

递归识别图片目录「打包单位」，将图片按序号规则重命名后以 ZIP_STORED（不压缩）打包为同级 `<dir>.zip`，完成后删除源目录。

#### 打包单位识别

| 类型 | 识别条件 | zip 内结构 |
|---|---|---|
| `flat` | 目录内仅图片，无子目录，且图片数 ≥ 最小阈值 | 图片直接置 zip 根目录 |
| `nested` | 目录内仅子目录，每个子目录为纯图片叶 | 保留子目录名作路径前缀；顶层 `cover.*` / `0000.*` / `ComicInfo.xml` 原名写入 zip 根 |

混合目录（图+子目录同层，且顶层图非 cover/0000 类）跳过；图片数不足的目录跳过；容器层（子目录不全是图片叶）自动下钻。

#### 序号规则

每个目录独立计数，从 `0001` 起步，4 位零填充（图片数 ≥ 10000 时自动扩位），扩展名保留原扩展名并小写。

```bash
# 批量预览（不修改文件）
manga-cli pack-pic --root /path/to/albums

# 批量执行（重命名 + 打包 + 删除源目录）
manga-cli pack-pic --root /path/to/albums --apply

# 并行 plan（plan 阶段；≥ 4 个单位时才真正启用）
manga-cli pack-pic --root /path/to/albums --apply --jobs 4
manga-cli pack-pic --root /path/to/albums --apply --jobs 0   # 自动 min(cpu, 4)
```

### std-title 子命令

```bash
# 批量预览（不修改文件）
manga-cli std-title --root /path/to/manga

# 批量执行
manga-cli std-title --root /path/to/manga --apply

# 内置解析示例（回归测试）
manga-cli std-title --examples

# 并行 plan（纯字符串处理为主，收益有限；主要用于大目录的进度反馈）
manga-cli std-title --root /path/to/manga --jobs 4
```

### make-cover 子命令

为 CBZ 写入一张 2:3 / ≤ 1000×1500 的 WebP 封面。目标文件名取决于源图：

| 源图 | 目标 | 行为 |
|---|---|---|
| `0001.*` | `0000.webp` | 追加新封面，按字典序排在所有页面之前 |
| `cover.*` | `0000.webp` | 写入新 `0000.webp` 并删除所有 `cover.*` 条目 |

**背景**：[grimmory](https://github.com/grimmory-tools/grimmory) 在生成封面时若源图超过 2000 万像素会拒绝处理：

```
Rejected image: dimensions 4000x5400 (21600000 pixels) exceed limit 20000000 — possible decompression bomb
```

本子命令产出的 WebP 严格命中 1000×1500（与 grimmory 内部封面目标尺寸 2:3 对齐），并以追加方式写入原 CBZ，不重建压缩包。源图小于 1000×1500 时保持原尺寸（不放大）。

```bash
# 预览
manga-cli make-cover --root /path/to/cbz

# 实际写入
manga-cli make-cover --root /path/to/cbz --apply

# smartcrop 显著性裁剪（横图保留主体更稳）
manga-cli make-cover --root /path/to/cbz --apply --smart

# 并行处理（plan 阶段；4 个文件以上才会真正启用）
manga-cli make-cover --root /path/to/cbz --apply --jobs 4
manga-cli make-cover --root /path/to/cbz --apply --jobs 0   # 自动 min(cpu, 4)
```

每处理一个 cbz 即打印进度行 `✅ [12/345] 文件名`，便于大批量任务跟踪。
plan 阶段是 CPU 密集的解码+裁剪+编码，apply 阶段（ZIP 追加）已经很快不并行。

#### 行为约定

| 项 | 值 |
|---|---|
| 写入文件名 | 源 `0001.*` 或 `cover.*` → `0000.webp`（cover.* 同时被删除） |
| 源图查找 | ZIP 根目录按优先级 `cover.*` → `0001.*`（不递归子目录） |
| 输出比例 | 2:3（宽:高） |
| 输出尺寸 | 1000×1500（源更小则保留原尺寸，不放大） |
| 写入方式 | ZIP 追加；同 stem 的旧条目（任何扩展名）成为死空间，与 ComicInfo.xml 同策略 |
| 处理范围 | `--root` 下所有 .cbz（递归子目录） |

#### 裁剪模式

| 模式 | 触发 | 说明 |
|---|---|---|
| `center`（默认） | 不加 `--smart` | 居中裁剪到 2:3，最简单、可预测；横图（如跨页扉页）可能丢主体 |
| `smart` | `--smart` | smartcrop 基于边缘 / 饱和度 / 肤色综合打分挑选最佳子矩形 |

### make-meta 子命令

生成 ComicInfo v2.1 XML，写入 CBZ 文件。

```bash
# 预览（不修改文件）
manga-cli make-meta --root /path/to/cbz

# 实际写入
manga-cli make-meta --root /path/to/cbz --apply

# 内置示例
manga-cli make-meta --examples

# 并行 plan（plan 阶段是 IO 密集 ZIP 扫描；大目录可加速）
manga-cli make-meta --root /path/to/cbz --apply --jobs 4
```

#### 字段映射与顺序

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
| `Notes` | `"metadata creator": "manga-cli 0.1.0"` |

---

## 配置文件位置

所有持久化配置统一落到 `<user_config>/media-toolkit/config/`：

| 文件 | 用途 |
|---|---|
| `artifact.json` | artifact 业务配置（workdirs 列表 + 搜索 URL 模板） |
| `manga.json` | manga 业务配置（当前为占位，预留后续业务字段） |
| `gui.json` | GUI 状态（路径历史、窗口几何等） |

Windows 下 `<user_config>` 为 `%LOCALAPPDATA%`。别名扫描缓存落在
同根目录的 `<user_config>/media-toolkit/cache/aliases.json`。

---

## 相关文档

- [DEVELOPMENT.md](DEVELOPMENT.md) — 源码安装、本地运行、测试、打包发布
- [ARCHITECTURE.md](ARCHITECTURE.md) — 项目结构与模块依赖关系

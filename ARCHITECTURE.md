# 项目结构与依赖关系

## 项目结构

```
base/                            — 跨业务共享基础设施
├── console.py                   — 终端输出 & GUI sink 路由（emit / warn / error / set_output）
├── doctor.py                    — 通用环境体检引擎（run_doctor，各 CLI 声明自身 checks）
├── drag_loop.py                 — 通用拖入循环（run_drag_loop）
├── fs.py                        — 文件系统工具（merge_into / move_dir / safe_rmtree）
├── config_paths.py              — 跨平台 user_config_dir() 定位
├── app_config.py                — 统一持久化目录 + JsonConfig 基类（gui/artifact/manga.json 共用）
└── gui/                         — 共享 GUI 组件（PySide6，可选）
    ├── shell.py                 — Shell(QMainWindow)：左侧 Tab 宿主，register_module()
    ├── app_check.py             — check_pyside6()：启动前依赖检查
    ├── log_view.py              — LogView：日志滚动文本框
    ├── qt_sink.py               — QtSink：console → LogView 桥接
    ├── path_picker.py           — PathPicker：路径选择 + 拖入 widget
    ├── worker.py                — BaseWorker(QThread)：通用后台任务
    └── config.py                — GUIConfig(JsonConfig)：gui.json 单例 + 路径历史 API

module/                          — 业务包命名空间
├── manga/                       — 漫画工具（manga toolkit）
│   ├── __init__.py              — 版本号（__version__）
│   ├── __main__.py              — 适配 `python -m module.manga` 的转发层
│   ├── cli/                     — CLI 入口 + 子命令实现（main = manga-cli）
│   │   ├── __init__.py          — build_parser() / main()
│   │   ├── std_title.py         — 标题标准化子命令
│   │   ├── make_meta.py         — 元数据写入子命令
│   │   ├── make_cover.py        — 封面写入子命令
│   │   └── pack_pic.py          — 图片打包子命令
│   ├── extras/                  — 旁路 / 辅助模块（非业务子命令）
│   │   ├── doctor.py            — doctor 子命令（环境体检）
│   │   └── examples.py          — 内置示例演示运行器（std-title / make-meta --examples 共用）
│   ├── gui/                     — 桌面 GUI（PySide6，可选依赖）
│   │   ├── __init__.py          — QApplication 入口（main = manga-gui）
│   │   ├── __main__.py          — `python -m module.manga.gui` / PyInstaller 入口
│   │   ├── module.py            — MangaModule（被 Shell 装载）
│   │   ├── tabs/                — 四个子命令各自 Tab
│   │   └── workers/             — QThread 阻塞任务包装
│   ├── core/                    — 纯数据层（无 I/O，无内部依赖）
│   │   ├── config.py            — 全局默认配置
│   │   ├── models.py            — Chapter / Volume / MangaInfo / *Plan 数据类
│   │   └── patterns.py          — 正则表达式常量与规则表
│   ├── infra/                   — 基础设施层（plan 调度 + 进度反馈）
│   │   └── parallel.py          — run_plans：进度行 + 可选并行
│   ├── naming/                  — 名称解析与构建
│   │   ├── parser.py            — parse_name(author, name) → MangaInfo
│   │   ├── builder.py           — build_new_name(info) → str
│   │   └── text.py              — 命名层字符串工具（繁简 / 归一化 / flag）
│   ├── presentation/            — 领域对象的终端渲染
│   │   └── view.py              — print_run_banner / print_*_preview / print_make_meta_diff_table
│   └── workflow/                — 高层工作流（每个子命令一个模块）
│       ├── std_title.py         — 源文件扫描、重命名执行
│       ├── make_meta.py         — ComicInfo.xml 生成 & 写入
│       ├── make_cover.py        — 封面查找、裁剪、WebP 编码、CBZ 追加写入
│       └── pack_pic.py          — 图片目录序号化 + STORED zip 打包
└── artifact/                    — 文件工具（artifact toolkit）
    ├── __init__.py
    ├── cli/                     — CLI 入口（main = artifact-cli）
    │   ├── __init__.py          — build_parser() / main()
    │   ├── classify.py          — classify 子命令
    │   └── doctor.py            — doctor 子命令（委托 base.doctor.run_doctor）
    ├── core/                    — 纯数据层（运行期配置 / 领域模型）
    │   └── runtime_config.py    — WorkDir / Config / load_config()（artifact.json）
    ├── gui/                     — 桌面 GUI（PySide6，可选依赖）
    │   ├── __init__.py          — QApplication 入口（main = artifact-gui）
    │   ├── module.py            — ArtifactModule（被 Shell 装载）
    │   ├── tabs/classify_tab.py — ClassifyTab：拖入区 + 工作目录面板
    │   └── widgets/             — drop_area / candidate_dialog
    └── workflow/classify/       — 归类工作流
        ├── path.py              — path_to_author_name()
        ├── alias.py             — scan_aliases()（扫描 [别名]：XX.txt）
        ├── matcher.py           — find_candidates()
        └── ops.py               — classify_one()

app/                             — 顶层双模块启动器
└── gui.py                       — main = app-gui（同窗口装载 manga + artifact）
```

> 命名约定：Python 模块名遵循 PEP 8（小写 + 下划线），暴露的 CLI 命令名遵循 Unix 惯例（小写 + 连字符）。
> `pyproject.toml` 中 `manga-cli = "module.manga.cli:main"`、`artifact-cli = "module.artifact.cli:main"` 即为两者的桥接。

## 依赖关系（低层 → 高层）

```
base/console · base/fs · base/drag_loop
        ↓
module/manga/core/{config,models,patterns}
        ↓
module/manga/infra/parallel            ← base/console
        ↓
module/manga/naming/{parser,builder,text}  ← module/manga/core · base/console
        ↓
module/manga/workflow/*                ← module/manga/core · module/manga/infra · module/manga/naming · module/manga/presentation · base/*
        ↓
module/manga/cli/__init__.py  (main → manga-cli)

module/artifact/workflow/classify/*  ← base/{console,fs,drag_loop}
        ↓
module/artifact/cli/__init__.py  (main → artifact-cli)

base/gui/{shell,worker,…}        ← base/console
module/manga/gui/module.py       ← module/manga/workflow/* · base/gui
module/artifact/gui/module.py    ← module/artifact/workflow/* · base/gui
        ↓
app/gui.py  (main → app-gui)  ← module/manga/gui · module/artifact/gui · base/gui
```

## 持久化目录

所有运行期可变状态统一落在 `<user_config>/media-toolkit/config/` 下三个 JSON：

```
%LOCALAPPDATA%/media-toolkit/config/           (Windows)
~/Library/Application Support/media-toolkit/config/    (macOS)
${XDG_CONFIG_HOME:-~/.config}/media-toolkit/config/    (Linux)
├── gui.json        — GUI 用户状态（PathPicker 历史 / 各 Tab jobs+quality+smart /
│                     splitter sizes / Shell 窗口几何）；平铺 key，无 schema
├── artifact.json   — artifact 业务配置（workdirs / search_url_template）；
│                     缺失时由 base.app_config.JsonConfig 落盘 {"artifact.workdirs": []}；
│                     GUI ClassifyTab 提供「📂 打开 artifact.json」按钮调系统关联
│                     程序编辑，编辑后点「🔄 刷新别名」即重新读取
└── manga.json      — manga 业务运行期配置；当前仅占位 {"$schema_version": 1}
```

任意入口（CLI / GUI）启动期都会触发 `get_manga_config()` / `load_config()`，确保
缺失时自动落盘。GUIConfig 同样在首次 `get_config()` 时落盘。

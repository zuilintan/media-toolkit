"""base — 跨业务模块的共通基础设施

为 mt（manga-toolkit）、ft（file-toolkit）等业务包共同使用的工具与基类。
子模块约定：
  - base.fs      — 文件/路径操作原语（纯标准库）
  - base.gui.*   — 通用 Qt 部件（懒导入，仅在装了 PySide6 时可用）
"""

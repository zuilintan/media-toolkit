"""
mt.gui — PySide6 桌面前端

完全复用 mt.workflow 的 plan/apply 函数，不再走 mt.cli.cmd_*
（cmd_* 内部用 input() 阻塞确认，不适配 GUI）。

模块布局:
    app.py           — QApplication 入口
    main_window.py   — QTabWidget 装配三个子命令
    qt_sink.py       — 接管 base.console.emit 的文本通道
    workers/         — QThread 后台任务包装
    widgets/         — 通用部件（LogView / PathPicker）
    tabs/            — 三个子命令独立 Tab
"""

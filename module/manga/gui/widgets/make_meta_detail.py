"""单个 :class:`~module.manga.core.models.MakeMetaPlan` 的完整详情对话框。

模态弹窗：复用 :class:`~base.gui.log_view.LogView` 渲染，同字体 / 同 ANSI
着色 / 同等宽对齐策略，与主 LogView 视觉一致。

工作流：
1. 临时把 :func:`~base.console.set_output` 切到本对话框自带的 :class:`~base.gui.qt_sink.QtSink`；
2. 调 :func:`~module.manga.presentation.view.emit_make_meta_card` 渲染；
3. 恢复主线程原 sink，避免影响 Tab 后续的 emit。

注意：调用方应在主线程触发；线程本地 sink 保证不会污染其他线程。
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

from base.console import get_output, set_output
from base.gui.log_view import LogView
from base.gui.qt_sink import QtSink
from module.manga.core.models import MakeMetaPlan
from module.manga.presentation.view import emit_make_meta_card


class MakeMetaDetailDialog(QDialog):
    """单 plan 的完整 diff 表格弹窗。"""

    def __init__(self, plan: MakeMetaPlan, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f'详情 — {plan.filename}')
        self.resize(900, 600)

        self._log = LogView(self)
        sink = QtSink(self)
        sink.text_written.connect(self._log.append_text)

        prev = get_output()
        set_output(sink)
        try:
            emit_make_meta_card(plan, 1)
            sink.flush()
        finally:
            set_output(prev)

        btns = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self._log, 1)
        lay.addWidget(btns)

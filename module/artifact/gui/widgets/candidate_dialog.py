"""候选目录单选对话框。

两种场景：0 候选 → 列 :class:`~module.artifact.workflow.classify.config.WorkDir`
让用户选"创建位置"；N 候选 → 列已有候选作者目录让用户选。业务 caller 在外层
把 0/N 分支转换成统一的"路径列表 + 提示语"传入；对话框自身不感知业务语义。
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)


class CandidateDialog(QDialog):
    """从 N 个 ``Path`` 中单选；通过 :meth:`selected_index` 取下标。"""

    def __init__(
        self,
        title: str,
        prompt: str,
        candidates: list[Path],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 320)

        self._list = QListWidget()
        for c in candidates:
            QListWidgetItem(str(c), self._list)
        if candidates:
            self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(self.accept)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(prompt))
        lay.addWidget(self._list)
        lay.addWidget(btns)

    def selected_index(self) -> int | None:
        row = self._list.currentRow()
        return row if row >= 0 else None


def ask_candidate(
    *,
    title: str,
    prompt: str,
    candidates: list[Path],
    parent: QWidget | None = None,
) -> Path | None:
    """便捷封装：弹出对话框 → 用户选确认 → 返回选定 ``Path``；取消返回 ``None``。"""
    dlg = CandidateDialog(title, prompt, candidates, parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    idx = dlg.selected_index()
    return candidates[idx] if idx is not None else None

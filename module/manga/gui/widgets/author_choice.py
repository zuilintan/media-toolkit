"""std_title GUI 的「作者选择对话框」。

scan 阶段（:meth:`~module.manga.gui.tabs.std_title_tab.StdTitleTab._validate_scan_target`）
对路径列表跑 :func:`~module.manga.workflow.std_title.derive_inputs`；某文件
``auto_author`` 为空时，:func:`resolve_author_via_dialog` 弹 :class:`AuthorChoiceDialog`
让用户在「父目录 / [] / 手动输入」之间选定。

drop / add 阶段不再做任何推导——输入列表退化为
:class:`~base.gui.path_list.PathListWidget`，与 make_meta / make_cover 三 Tab 对齐。
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QLabel,
    QLineEdit, QMessageBox, QRadioButton, QVBoxLayout, QWidget,
)

from module.manga.workflow.std_title import AuthorDerivation


class AuthorChoiceDialog(QDialog):
    """让用户在「父目录 / [] / 手动输入」中选择作者。

    返回 ``(author, publisher)``；用户取消返回 ``('', '')``。
    """

    def __init__(self, path: Path, deriv: AuthorDerivation, parent=None) -> None:
        super().__init__(parent)
        title = ('选择作者（推导冲突）' if deriv.conflict
                 else '选择作者（无法自动推导）')
        self.setWindowTitle(title)
        self.setModal(True)
        self._deriv = deriv
        self._chosen_author    = ''
        self._chosen_publisher = ''

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'📄 {path.name}'))
        lay.addWidget(QLabel('请选择作者来源:'))

        self._group   = QButtonGroup(self)
        self._options: list[tuple[QRadioButton, str, str]] = []   # (rb, author, publisher)

        if deriv.parent_author:
            rb = QRadioButton(f'父目录: {deriv.parent_author}')
            lay.addWidget(rb)
            self._group.addButton(rb)
            self._options.append((rb, deriv.parent_author, ''))

        if deriv.bracket_author:
            pub  = deriv.bracket_publisher
            text = f'[]: {deriv.bracket_author}' + (
                f'  (社团: {pub})' if pub else ''
            )
            rb   = QRadioButton(text)
            lay.addWidget(rb)
            self._group.addButton(rb)
            self._options.append((rb, deriv.bracket_author, pub))

        self._manual_rb = QRadioButton('手动输入:')
        lay.addWidget(self._manual_rb)
        self._group.addButton(self._manual_rb)

        self._manual_edit = QLineEdit()
        self._manual_edit.setPlaceholderText('作者名')
        self._manual_edit.textEdited.connect(
            lambda *_: self._manual_rb.setChecked(True)
        )
        lay.addWidget(self._manual_edit)

        if self._options:
            self._options[0][0].setChecked(True)
        else:
            self._manual_rb.setChecked(True)

        bb = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_accept(self) -> None:
        for rb, a, pub in self._options:
            if rb.isChecked():
                self._chosen_author    = a
                self._chosen_publisher = pub
                self.accept()
                return
        if self._manual_rb.isChecked():
            text = self._manual_edit.text().strip()
            if not text:
                QMessageBox.warning(self, '提示', '请填写作者名')
                return
            self._chosen_author    = text
            self._chosen_publisher = ''
            self.accept()
            return
        # 兜底：理论上至少有一个 checked
        self.reject()

    def result_author(self) -> tuple[str, str]:
        """返回 ``(author, publisher)``；对话框被取消时为 ``('', '')``。"""
        return self._chosen_author, self._chosen_publisher


def resolve_author_via_dialog(
    parent: QWidget, path: Path, deriv: AuthorDerivation,
) -> tuple[str, str] | None:
    """:func:`~module.manga.workflow.std_title.derive_inputs` 的 GUI 回调。

    弹 :class:`AuthorChoiceDialog` 让用户选定；取消即返回 ``None`` → ``derive_inputs``
    跳过该文件。
    """
    dlg = AuthorChoiceDialog(path, deriv, parent=parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    a, pub = dlg.result_author()
    return (a, pub) if a else None

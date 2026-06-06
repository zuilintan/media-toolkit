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
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QLabel,
    QLineEdit, QMessageBox, QRadioButton, QVBoxLayout, QWidget,
)

from module.manga.workflow.std_title import AuthorDerivation


class AuthorChoiceDialog(QDialog):
    """让用户在「父目录 / [] / 手动输入」中选择作者。

    返回 ``(author, publisher, apply_to_all_source)``；用户取消时三者均为 ``''``。
    ``apply_to_all_source`` 取 ``'parent'`` / ``'bracket'`` / ``''``——非空时调用方
    应在后续同类待选文件上按该来源短路弹窗。
    """

    def __init__(self, path: Path, deriv: AuthorDerivation, parent=None) -> None:
        super().__init__(parent)
        title = ('选择作者（推导冲突）' if deriv.conflict
                 else '选择作者（无法自动推导）')
        self.setWindowTitle(title)
        self.setModal(True)
        self._deriv = deriv
        self._chosen_author       = ''
        self._chosen_publisher    = ''
        self._apply_to_all_source = ''

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'📄 {path.name}'))
        lay.addWidget(QLabel('请选择作者来源:'))

        self._group   = QButtonGroup(self)
        # (rb, author, publisher, source)；source 为 'parent'/'bracket'，
        # 标识"全部应用"勾选后供调用方短路的规则键
        self._options: list[tuple[QRadioButton, str, str, str]] = []

        if deriv.parent_author:
            rb = QRadioButton(f'父目录: {deriv.parent_author}')
            lay.addWidget(rb)
            self._group.addButton(rb)
            self._options.append((rb, deriv.parent_author, '', 'parent'))

        if deriv.bracket_author:
            pub  = deriv.bracket_publisher
            text = f'[]: {deriv.bracket_author}' + (
                f'  (社团: {pub})' if pub else ''
            )
            rb   = QRadioButton(text)
            lay.addWidget(rb)
            self._group.addButton(rb)
            self._options.append((rb, deriv.bracket_author, pub, 'bracket'))

        self._manual_rb = QRadioButton('手动输入:')
        lay.addWidget(self._manual_rb)
        self._group.addButton(self._manual_rb)

        self._manual_edit = QLineEdit()
        self._manual_edit.setPlaceholderText('作者名')
        self._manual_edit.textEdited.connect(
            lambda *_: self._manual_rb.setChecked(True)
        )
        lay.addWidget(self._manual_edit)

        # 「全部应用」：仅父目录 / [] 这类"按来源可重复套用"的选择可启用；
        # 手动输入逐文件无法套用，选中时禁用并清掉勾选
        self._apply_all_cb = QCheckBox('对后续同类文件自动应用此选择')
        self._apply_all_cb.setToolTip(
            '勾选后，剩余待选文件若同样能从该来源（父目录 / []）自动取到作者，'
            '将按本次选择短路；仍需手动输入的文件会再次弹窗。'
        )
        lay.addWidget(self._apply_all_cb)
        self._group.buttonClicked.connect(self._sync_apply_all_enabled)

        if self._options:
            self._options[0][0].setChecked(True)
        else:
            self._manual_rb.setChecked(True)
        self._sync_apply_all_enabled()

        bb = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _sync_apply_all_enabled(self, *_) -> None:
        """手动输入选项不可"全部应用"——选中时禁用并清掉勾选。"""
        is_manual = self._manual_rb.isChecked()
        self._apply_all_cb.setEnabled(not is_manual)
        if is_manual:
            self._apply_all_cb.setChecked(False)

    def _on_accept(self) -> None:
        for rb, a, pub, source in self._options:
            if rb.isChecked():
                self._chosen_author    = a
                self._chosen_publisher = pub
                if self._apply_all_cb.isChecked():
                    self._apply_to_all_source = source
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

    def result_author(self) -> tuple[str, str, str]:
        """返回 ``(author, publisher, apply_to_all_source)``；取消时三者均为 ``''``。"""
        return (self._chosen_author, self._chosen_publisher,
                self._apply_to_all_source)


def resolve_author_via_dialog(
    parent: QWidget, path: Path, deriv: AuthorDerivation,
) -> tuple[str, str, str] | None:
    """:func:`~module.manga.workflow.std_title.derive_inputs` 的 GUI 回调。

    弹 :class:`AuthorChoiceDialog` 让用户选定；取消即返回 ``None`` → ``derive_inputs``
    跳过该文件。返回 ``(author, publisher, apply_to_all_source)`` 三元组——
    ``apply_to_all_source`` 非空时，调用方应在后续同类待选文件上按该来源短路弹窗。
    """
    dlg = AuthorChoiceDialog(path, deriv, parent=parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    a, pub, source = dlg.result_author()
    return (a, pub, source) if a else None

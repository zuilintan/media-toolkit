"""std_title GUI 的「输入列表」控件与作者选择对话框。

:class:`InputListWidget` 替代 :class:`~base.gui.path_picker.PathPicker`，支持
按文件 / 目录两种方式增量添加，每行记录 :class:`~module.manga.workflow.std_title.StdTitleInput`。

:class:`AuthorChoiceDialog` 在作者推导冲突 / 缺失时弹出，列出候选项 + 手填项，
返回 ``(author, publisher)``。
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
    QRadioButton, QVBoxLayout, QWidget,
)

from base.gui.palette import PRIMARY

from module.manga.core.config import FILE_EXTS
from module.manga.workflow.std_title import (
    AuthorDerivation, StdTitleInput,
    build_input, derive_author,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 作者选择对话框（冲突 / 缺失场景）
# ═══════════════════════════════════════════════════════════════════════════════

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

        # 默认勾选第一个候选；都没有则默认手填
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
    """对单个文件运行作者推导：能自动推导直接返回，否则弹窗。

    :return: ``(author, publisher)``；用户在弹窗中取消返回 ``None``。
    """
    author = deriv.auto_author
    if author:
        pub = (deriv.bracket_publisher
               if author == deriv.bracket_author else '')
        return author, pub

    dlg = AuthorChoiceDialog(path, deriv, parent=parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    a, pub = dlg.result_author()
    return (a, pub) if a else None


# ═══════════════════════════════════════════════════════════════════════════════
# 输入列表控件
# ═══════════════════════════════════════════════════════════════════════════════

class InputListWidget(QWidget):
    """已添加的 :class:`StdTitleInput` 列表，支持文件 / 目录两种增量添加方式。

    «添加» 按钮含菜单（``添加文件… / 添加目录…``）；目录模式按现有「库根 →
    作者子目录」结构展开。每个文件添加时自动调用 :func:`resolve_author_via_dialog`，
    冲突 / 缺失会弹窗交互。
    """

    inputs_changed = Signal()   # 列表项变更时发出，供外部更新按钮态

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._inputs: list[StdTitleInput] = []
        self.setAcceptDrops(True)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)

        # 添加按钮 + 二级菜单
        self._add_btn  = QPushButton('添加…')
        self._add_menu = QMenu(self._add_btn)
        act_file = QAction('添加文件…', self)
        act_dir  = QAction('添加目录…', self)
        act_file.triggered.connect(self._add_files)
        act_dir.triggered.connect(self._add_dir)
        self._add_menu.addAction(act_file)
        self._add_menu.addAction(act_dir)
        self._add_btn.setMenu(self._add_menu)

        self._remove_btn = QPushButton('移除选中')
        self._clear_btn  = QPushButton('清空')
        self._remove_btn.clicked.connect(self._remove_selected)
        self._clear_btn.clicked.connect(self.clear)

        btn_lay = QHBoxLayout()
        btn_lay.addWidget(self._add_btn)
        btn_lay.addWidget(self._remove_btn)
        btn_lay.addWidget(self._clear_btn)
        btn_lay.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(btn_lay)
        lay.addWidget(self._list, 1)

    # ── 公共 API ──────────────────────────────────────────────────────
    def inputs(self) -> list[StdTitleInput]:
        return list(self._inputs)

    def clear(self) -> None:
        self._inputs.clear()
        self._list.clear()
        self.inputs_changed.emit()

    # ── 添加流程 ──────────────────────────────────────────────────────
    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, '添加文件', '',
            'ZIP/CBZ (*.zip *.cbz);;所有文件 (*)',
        )
        if files:
            self._add_paths([Path(f) for f in files])

    def _add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, '添加目录', '')
        if not d:
            return
        self._add_dirs_smart([Path(d)])

    def _add_dirs_smart(self, dirs: list[Path]) -> None:
        """对每个目录智能展开：直接含 ``.zip/.cbz`` → 作者目录；否则视为库根。

        与原 ``_add_dir`` 行为一致，抽出供拖放复用。
        """
        paths: list[Path] = []
        for root in dirs:
            direct = [p for p in root.iterdir()
                      if p.is_file() and p.suffix.lower() in FILE_EXTS]
            if direct:
                paths.extend(sorted(direct))
            else:
                for sub in sorted(root.iterdir()):
                    if not sub.is_dir():
                        continue
                    paths.extend(
                        p for p in sorted(sub.iterdir())
                        if p.is_file() and p.suffix.lower() in FILE_EXTS
                    )
        if not paths:
            QMessageBox.information(
                self, '提示',
                '目录内未找到 .zip / .cbz 文件',
            )
            return
        self._add_paths(paths)

    def _add_dirs_as_files(self, dirs: list[Path]) -> None:
        """把每个目录视为「文件容器」：仅取其直接子项中的 ``.zip/.cbz``。

        不向下钻；仅一层。供拖放时用户选「文件」分支调用。
        """
        paths: list[Path] = []
        for root in dirs:
            paths.extend(sorted(
                p for p in root.iterdir()
                if p.is_file() and p.suffix.lower() in FILE_EXTS
            ))
        if not paths:
            QMessageBox.information(
                self, '提示',
                '所选目录内未找到 .zip / .cbz 文件',
            )
            return
        self._add_paths(paths)

    def _add_paths(self, paths: list[Path]) -> None:
        """对每个路径运行作者推导，弹窗解决冲突 / 缺失，加入列表。

        用户在弹窗中取消 → 跳过该项（其它继续）。
        """
        added = 0
        for p in paths:
            if p.suffix.lower() not in FILE_EXTS:
                continue
            deriv  = derive_author(str(p))
            chosen = resolve_author_via_dialog(self, p, deriv)
            if chosen is None:
                continue
            author, publisher = chosen
            inp = build_input(str(p), author, publisher)
            self._inputs.append(inp)
            self._append_list_item(inp)
            added += 1
        if added:
            self.inputs_changed.emit()

    def _append_list_item(self, inp: StdTitleInput) -> None:
        name      = Path(inp.src_path).name
        rel_dir   = Path(inp.author_dir).name
        publisher = (Path(inp.publisher_file).stem
                     if inp.publisher_file else '')
        label     = f'{name}   →   {rel_dir}/  [{inp.author}]'
        if publisher:
            label += f'   📌 {publisher}'
        item = QListWidgetItem(label)
        item.setToolTip(inp.src_path)
        self._list.addItem(item)

    # ── 拖放 ──────────────────────────────────────────────────────────
    def _collect_drop_paths(self, e: QDropEvent | QDragEnterEvent) -> list[Path]:
        if not e.mimeData().hasUrls():
            return []
        paths: list[Path] = []
        for url in e.mimeData().urls():
            if url.isLocalFile():
                p = Path(url.toLocalFile())
                if p.exists():
                    paths.append(p)
        return paths

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:   # noqa: N802 — Qt API 命名
        paths = self._collect_drop_paths(e)
        if not paths:
            e.ignore()
            return
        # 至少一项是目录、或是受支持的文件即接受
        usable = any(
            p.is_dir() or (p.is_file() and p.suffix.lower() in FILE_EXTS)
            for p in paths
        )
        if not usable:
            e.ignore()
            return
        self._list.setStyleSheet(f'QListWidget {{ border: 2px solid {PRIMARY}; }}')
        e.acceptProposedAction()

    def dragLeaveEvent(self, e: QDragLeaveEvent) -> None:   # noqa: N802 — Qt API 命名
        self._list.setStyleSheet('')
        e.accept()

    def dropEvent(self, e: QDropEvent) -> None:   # noqa: N802 — Qt API 命名
        self._list.setStyleSheet('')
        paths = self._collect_drop_paths(e)
        if not paths:
            e.ignore()
            return
        files = [p for p in paths
                 if p.is_file() and p.suffix.lower() in FILE_EXTS]
        dirs  = [p for p in paths if p.is_dir()]

        # 文件直接加（无歧义）
        if files:
            self._add_paths(files)

        if dirs:
            mode = self._ask_folder_mode(dirs)
            if mode == 'files':
                self._add_dirs_as_files(dirs)
            elif mode == 'dirs':
                self._add_dirs_smart(dirs)
            # mode is None → 用户取消

        e.acceptProposedAction()

    def _ask_folder_mode(self, dirs: list[Path]) -> str | None:
        """文件夹拖入时弹窗让用户选择处理方式。

        :return: ``'files'`` / ``'dirs'`` / ``None`` (取消)
        """
        names = '、'.join(d.name for d in dirs[:3])
        if len(dirs) > 3:
            names += f' 等 {len(dirs)} 项'
        box = QMessageBox(self)
        box.setWindowTitle('文件夹拖入')
        box.setIcon(QMessageBox.Question)
        box.setText(f'已拖入文件夹：{names}')
        box.setInformativeText(
            '请选择视作：\n'
            '  • 文件 — 取其直接子项中的 .zip / .cbz（不递归）\n'
            '  • 目录 — 作为「作者目录」或「库根」智能扫描'
        )
        btn_files = box.addButton('文件', QMessageBox.AcceptRole)
        btn_dirs  = box.addButton('目录', QMessageBox.AcceptRole)
        btn_cancel = box.addButton('取消', QMessageBox.RejectRole)
        box.setDefaultButton(btn_dirs)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_files:
            return 'files'
        if clicked is btn_dirs:
            return 'dirs'
        return None

    def _remove_selected(self) -> None:
        rows = sorted(
            (self._list.row(i) for i in self._list.selectedItems()),
            reverse=True,
        )
        for r in rows:
            self._list.takeItem(r)
            del self._inputs[r]
        if rows:
            self.inputs_changed.emit()

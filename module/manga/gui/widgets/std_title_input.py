"""std_title GUI 的「输入列表」控件与作者选择对话框。

:class:`InputListWidget` 替代 :class:`~base.gui.path_picker.PathPicker`，支持
按「漫画文件 / 漫画作者文件夹」两种语义增量添加。

:class:`AuthorChoiceDialog`：单文件场景，作者推导冲突 / 缺失时弹出。
:class:`BatchAuthorChoiceDialog`：拖入文件夹且视作「漫画文件」时弹一次，
所有文件按所选策略统一处理（自动 [] 推导 / 统一用文件夹名 / 统一手填）。
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
# 单文件作者选择对话框（冲突 / 缺失场景）
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
# 批量作者策略对话框（漫画文件 / 拖入文件夹场景）
# ═══════════════════════════════════════════════════════════════════════════════

#: 策略标识：``'bracket'`` 自动从 ``[]`` 抽取 / ``'parent'`` 父目录名 / ``'manual'`` 手填
BatchStrategy = tuple[str, str]   # (kind, manual_author)


class BatchAuthorChoiceDialog(QDialog):
    """批量作者策略选择：让用户一次性决定一批文件的作者来源。

    三种策略:

    - ``bracket`` 自动从文件名 ``[作者]`` / ``[社团 (作者)]`` 抽取（无 ``[]`` 跳过）
    - ``parent``  统一使用文件夹名作为作者（多文件夹时各文件用其父目录名）
    - ``manual``  统一使用手填的同一作者名

    返回 :data:`BatchStrategy`；用户取消返回 ``None``。
    """

    def __init__(
        self, n_files: int, folder_label: str = '', parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle('批量作者来源')
        self.setModal(True)
        self._result: BatchStrategy | None = None

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'共 {n_files} 个漫画文件，请选择作者来源：'))

        self._rb_bracket = QRadioButton(
            '自动推导（从文件名 [作者] / [社团 (作者)] 抽取；无 [] 的文件跳过）'
        )
        parent_label = (f'统一使用文件夹名: {folder_label}' if folder_label
                        else '统一使用各文件父目录名')
        self._rb_parent  = QRadioButton(parent_label)
        self._rb_manual  = QRadioButton('统一手动输入:')

        self._manual_edit = QLineEdit()
        self._manual_edit.setPlaceholderText('作者名')
        self._manual_edit.textEdited.connect(
            lambda *_: self._rb_manual.setChecked(True)
        )

        self._group = QButtonGroup(self)
        for rb in (self._rb_bracket, self._rb_parent, self._rb_manual):
            self._group.addButton(rb)
            lay.addWidget(rb)
        lay.addWidget(self._manual_edit)
        # 默认「统一使用文件夹名」：拖入文件夹的最常见语义即「作者文件夹」
        self._rb_parent.setChecked(True)

        bb = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_accept(self) -> None:
        if self._rb_bracket.isChecked():
            self._result = ('bracket', '')
        elif self._rb_parent.isChecked():
            self._result = ('parent', '')
        else:
            text = self._manual_edit.text().strip()
            if not text:
                QMessageBox.warning(self, '提示', '请填写作者名')
                return
            self._result = ('manual', text)
        self.accept()

    def result_strategy(self) -> BatchStrategy | None:
        return self._result


# ═══════════════════════════════════════════════════════════════════════════════
# 输入列表控件
# ═══════════════════════════════════════════════════════════════════════════════

class InputListWidget(QWidget):
    """已添加的 :class:`StdTitleInput` 列表。

    «添加…» 按钮含菜单（``添加漫画文件… / 添加漫画作者文件夹…``）：

    - **添加漫画文件**：多选 ``.zip/.cbz`` 文件，逐文件自动 derive，
      冲突 / 缺失时弹 :class:`AuthorChoiceDialog`
    - **添加漫画作者文件夹**：选目录，目录名即作者，下层 ``.zip/.cbz`` 全录入，不弹窗
      （快速通道，用户明确"这是作者目录"时用）

    支持拖放：纯文件按「漫画文件」语义；含文件夹时直接弹
    :class:`BatchAuthorChoiceDialog`（默认选「统一用文件夹名」，等价于
    「漫画作者文件夹」语义；用户可改选 ``[]`` 自动推导 / 手填）。
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
        act_file = QAction('添加漫画文件…', self)
        act_dir  = QAction('添加漫画作者文件夹…', self)
        act_file.triggered.connect(self._add_manga_files)
        act_dir.triggered.connect(self._add_author_folder)
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
    def _add_manga_files(self) -> None:
        """add menu「添加漫画文件…」：多选文件，逐文件 derive + 弹窗。"""
        files, _ = QFileDialog.getOpenFileNames(
            self, '添加漫画文件', '',
            'ZIP/CBZ (*.zip *.cbz);;所有文件 (*)',
        )
        if files:
            self._add_paths_per_file([Path(f) for f in files])

    def _add_author_folder(self) -> None:
        """add menu「添加漫画作者文件夹…」：目录名即作者，下层文件全录入。"""
        d = QFileDialog.getExistingDirectory(self, '添加漫画作者文件夹', '')
        if not d:
            return
        self._add_author_folders([Path(d)])

    # ── 漫画作者文件夹批量录入（不弹窗） ─────────────────────────────
    def _add_author_folders(self, dirs: list[Path]) -> None:
        """每个目录的 ``name`` 作为作者，下层 ``.zip/.cbz`` 直接录入。

        publisher 仍按文件名 ``[社团 (作者)]`` 抽取（社团信息不丢失）。
        """
        added = 0
        empty_dirs: list[str] = []
        for root in dirs:
            author = root.name
            files  = sorted(
                p for p in root.iterdir()
                if p.is_file() and p.suffix.lower() in FILE_EXTS
            )
            if not files:
                empty_dirs.append(root.name)
                continue
            for f in files:
                deriv = derive_author(str(f))
                inp   = build_input(str(f), author, deriv.bracket_publisher)
                self._inputs.append(inp)
                self._append_list_item(inp)
                added += 1
        if added:
            self.inputs_changed.emit()
        if empty_dirs:
            QMessageBox.information(
                self, '提示',
                '以下文件夹内未找到 .zip / .cbz 文件：\n  '
                + '\n  '.join(empty_dirs),
            )

    # ── 漫画文件批量录入（弹一次策略窗，套用所有文件） ───────────────
    def _add_files_in_folders_batch(self, dirs: list[Path]) -> None:
        files: list[Path] = []
        for d in dirs:
            files.extend(sorted(
                p for p in d.iterdir()
                if p.is_file() and p.suffix.lower() in FILE_EXTS
            ))
        if not files:
            QMessageBox.information(
                self, '提示', '所选文件夹内未找到 .zip / .cbz 文件',
            )
            return

        folder_label = dirs[0].name if len(dirs) == 1 else ''
        dlg = BatchAuthorChoiceDialog(len(files), folder_label, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        strategy = dlg.result_strategy()
        if strategy is None:
            return
        self._apply_batch_strategy(files, strategy)

    def _apply_batch_strategy(
        self, files: list[Path], strategy: BatchStrategy,
    ) -> None:
        kind, manual = strategy
        added = skipped = 0
        for f in files:
            deriv = derive_author(str(f))
            if kind == 'bracket':
                if not deriv.bracket_author:
                    skipped += 1
                    continue
                author, publisher = deriv.bracket_author, deriv.bracket_publisher
            elif kind == 'parent':
                if not deriv.parent_author:
                    skipped += 1
                    continue
                author    = deriv.parent_author
                publisher = deriv.bracket_publisher   # 仍允许抽社团
            else:  # manual
                author    = manual
                publisher = deriv.bracket_publisher
            inp = build_input(str(f), author, publisher)
            self._inputs.append(inp)
            self._append_list_item(inp)
            added += 1
        if added:
            self.inputs_changed.emit()
        if skipped:
            QMessageBox.information(
                self, '部分跳过',
                f'已跳过 {skipped} 个文件（按所选策略无法推导作者）',
            )

    # ── 逐文件 derive + 弹窗（add menu 选文件 + 拖入纯文件） ─────────
    def _add_paths_per_file(self, paths: list[Path]) -> None:
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

        # 文件按「漫画文件」逐项处理（与 add menu 一致）
        if files:
            self._add_paths_per_file(files)

        if dirs:
            # 直接走批量策略窗：默认「统一使用文件夹名」== 漫画作者文件夹语义；
            # 用户改选 [] / 手填即可覆盖另两种场景，无需先做一次路由选择
            self._add_files_in_folders_batch(dirs)

        e.acceptProposedAction()

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

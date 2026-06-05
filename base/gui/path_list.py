""":class:`PathListWidget` —— 通用「路径列表 + 添加按钮 + 拖放」控件。

替代 :class:`~base.gui.path_picker.PathPicker` 的「单路径」语义,适合
make_cover / make_meta / pack_pic 等需要按多个文件 / 目录精准入参的场景。

行为按构造参数适配:

- ``accept_file_exts``:``None`` 接受任意文件;``()`` 不接受文件;
  ``('.cbz',)`` 仅接受 ``.cbz``。
- ``accept_dirs``:是否接受目录(拖放 + 「添加目录」按钮)。
- ``expand_dirs_on_add``:目录在添加阶段是否 ``rglob`` 展开成文件
  (仅当 ``accept_file_exts`` 非空时生效);列表项始终是「最终参与处理」的路径。

特化版本(含元数据 / 多源等)请单独写,不要继承本类(组合更清晰):scan 阶段
跑作者推导的 std_title Tab 复用本类作为输入控件,作者解析延后到
:meth:`~module.manga.gui.tabs.std_title_tab.StdTitleTab._validate_scan_target`
做。
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from base.gui.palette import PRIMARY
from module.artifact.gui.widgets.drop_area import urls_to_paths


class PathListWidget(QWidget):
    """已添加的路径列表,支持「添加」按钮与拖放。"""

    paths_changed = Signal()   # 列表项变更时发出,供外部更新按钮态

    def __init__(
        self,
        accept_file_exts: tuple[str, ...] | None,
        accept_dirs: bool,
        expand_dirs_on_add: bool = False,
        file_dialog_filter: str = '所有文件 (*)',
        file_dialog_title: str = '添加文件',
        dir_dialog_title:  str = '添加目录',
        add_file_label:    str = '添加文件…',
        add_dir_label:     str = '添加目录…',
        parent=None,
    ) -> None:
        super().__init__(parent)
        if accept_file_exts is None:
            self._exts: frozenset[str] | None = None
        else:
            self._exts = frozenset(e.lower() for e in accept_file_exts)
        self._accept_dirs       = accept_dirs
        self._expand_dirs_on_add = expand_dirs_on_add
        self._file_dialog_filter = file_dialog_filter
        self._file_dialog_title  = file_dialog_title
        self._dir_dialog_title   = dir_dialog_title

        self._paths: list[Path] = []
        self.setAcceptDrops(True)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        # 默认 sizeHint 约 256 px，对横排上下叠加的 GUI 偏高；锁个上限让输入区
        # 紧凑——长列表仍可滚动浏览
        self._list.setMaximumHeight(85)

        # 「添加」按钮:文件 + 目录都启用 → 二级菜单;仅一个 → 按钮直点
        accepts_file = self._exts is None or len(self._exts) > 0
        self._add_btn = QPushButton('添加…')
        if accepts_file and accept_dirs:
            menu = QMenu(self._add_btn)
            act_f = QAction(add_file_label, self)
            act_d = QAction(add_dir_label,  self)
            act_f.triggered.connect(self._pick_files)
            act_d.triggered.connect(self._pick_dir)
            menu.addAction(act_f)
            menu.addAction(act_d)
            self._add_btn.setMenu(menu)
        elif accepts_file:
            self._add_btn.setText(add_file_label)
            self._add_btn.clicked.connect(self._pick_files)
        elif accept_dirs:
            self._add_btn.setText(add_dir_label)
            self._add_btn.clicked.connect(self._pick_dir)
        else:
            # 不接受文件也不接受目录 —— 配置矛盾,按钮直接禁用
            self._add_btn.setEnabled(False)

        self._remove_btn = QPushButton('移除选中')
        self._clear_btn  = QPushButton('清空')
        self._remove_btn.clicked.connect(self._remove_selected)
        self._clear_btn.clicked.connect(self.clear)

        # 按钮交由外部（base_tab）摆放到输入区右侧；本控件内部只剩列表
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list, 1)

    def action_buttons(self) -> list[QPushButton]:
        """供外部（:class:`~module.manga.gui.tabs.base_tab.BaseTab`）取走按钮，
        统一摆到输入区右侧的纵向按钮列。"""
        return [self._add_btn, self._remove_btn, self._clear_btn]

    # ── 公共 API ──────────────────────────────────────────────────────
    def paths(self) -> list[Path]:
        return list(self._paths)

    def clear(self) -> None:
        if not self._paths:
            return
        self._paths.clear()
        self._list.clear()
        self.paths_changed.emit()

    def add_paths(self, paths: list[Path]) -> None:
        """增量添加;按当前 accept_* 配置过滤与展开后落入列表。"""
        added = 0
        for p in paths:
            added += self._add_one(p)
        if added:
            self.paths_changed.emit()

    # ── 添加按钮回调 ──────────────────────────────────────────────────
    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, self._file_dialog_title, '', self._file_dialog_filter,
        )
        if files:
            self.add_paths([Path(f) for f in files])

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self._dir_dialog_title, '')
        if d:
            self.add_paths([Path(d)])

    # ── 添加策略 ──────────────────────────────────────────────────────
    def _accepts(self, p: Path) -> bool:
        """该路径是否符合接受策略（文件按扩展名 / 目录按 accept_dirs）。"""
        if p.is_file():
            if self._exts is None:
                return True
            return bool(self._exts) and p.suffix.lower() in self._exts
        if p.is_dir():
            return self._accept_dirs
        return False

    def _add_one(self, p: Path) -> int:
        """返回新增的列表项数。"""
        if not self._accepts(p):
            return 0
        if p.is_file():
            self._append(p)
            return 1
        # 是目录且已 accept
        if self._expand_dirs_on_add and self._exts:
            # 按扩展名 rglob，每种扩展名各一次；比 rglob('*') 全扫再过滤显著少 I/O
            raw: list[Path] = []
            for ext in self._exts:
                raw.extend(p.rglob(f'*{ext}'))
            files = sorted(set(raw))
            for f in files:
                self._append(f)
            return len(files)
        self._append(p)
        return 1

    def _append(self, p: Path) -> None:
        item = QListWidgetItem(str(p))
        item.setToolTip(str(p))
        item.setData(Qt.UserRole, p)
        self._list.addItem(item)
        self._paths.append(p)

    # ── 拖放 ──────────────────────────────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent) -> None:   # noqa: N802 — Qt API 命名
        paths = urls_to_paths(e.mimeData().urls())
        if not paths or not any(self._accepts(p) for p in paths):
            e.ignore()
            return
        self._list.setStyleSheet(f'QListWidget {{ border: 2px solid {PRIMARY}; }}')
        e.acceptProposedAction()

    def dragLeaveEvent(self, e: QDragLeaveEvent) -> None:   # noqa: N802 — Qt API 命名
        self._list.setStyleSheet('')
        e.accept()

    def dropEvent(self, e: QDropEvent) -> None:   # noqa: N802 — Qt API 命名
        self._list.setStyleSheet('')
        paths = urls_to_paths(e.mimeData().urls())
        if not paths:
            e.ignore()
            return
        self.add_paths(paths)
        e.acceptProposedAction()

    # ── 选中移除 ──────────────────────────────────────────────────────
    def _remove_selected(self) -> None:
        items = self._list.selectedItems()
        if not items:
            return
        drop = {id(item.data(Qt.UserRole)) for item in items}
        self._paths = [p for p in self._paths if id(p) not in drop]
        for item in items:
            self._list.takeItem(self._list.row(item))
        self.paths_changed.emit()

    # ── 提示对话框(供子类 / 调用方使用) ────────────────────────────
    def show_info(self, text: str) -> None:
        QMessageBox.information(self, '提示', text)

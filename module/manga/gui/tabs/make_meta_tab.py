"""元数据写入 GUI Tab；复用 :mod:`module.manga.workflow.make_meta`。

输入语义：PathListWidget（接受 .cbz 文件 + 目录；目录在添加时 rglob 展开成 .cbz）。
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from base.console import emit, set_output
from base.gui.path_list import PathListWidget
from module.manga.core.models import MakeMetaPlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.gui.widgets.make_meta_detail import MakeMetaDetailDialog
from module.manga.gui.widgets.make_meta_tree import MakeMetaTree
from module.manga.presentation.export import export_plans
from module.manga.presentation.view import print_make_meta_preview
from module.manga.workflow.make_meta import (
    apply_plan, apply_plans, preview_plans_for_files,
)


class MakeMetaTab(BaseTab):
    cmd_name        = 'make_meta'
    apply_btn_text  = '执行'
    confirm_verb    = '执行'
    no_change_msg   = '没有需要写入的文件'

    def _create_input_widget(self) -> QWidget:
        self._input_list = PathListWidget(
            accept_file_exts=('.cbz',),
            accept_dirs=True,
            expand_dirs_on_add=True,
            file_dialog_filter='CBZ (*.cbz);;所有文件 (*)',
            file_dialog_title='添加 CBZ 文件',
            dir_dialog_title='添加 CBZ 根目录（递归扫描 .cbz）',
            add_file_label='添加 CBZ 文件…',
            add_dir_label='添加 CBZ 根目录…',
        )
        self._input_list.paths_changed.connect(self._on_inputs_changed)
        return self._input_list

    def _validate_scan_target(self) -> Any | None:
        files = [str(p) for p in self._input_list.paths()]
        if not files:
            QMessageBox.warning(self, '提示', '请先添加 .cbz 文件或包含 .cbz 的目录')
            return None
        return files

    def _format_banner_target(self, target: Any) -> object:
        return f'已添加 {len(target)} 个文件'

    def _has_inputs(self) -> bool:
        return bool(self._input_list.paths())

    def _on_inputs_changed(self) -> None:
        super()._on_inputs_changed()
        if not self._has_inputs():
            self._tree.set_plans([])
            self._export_btn.setEnabled(False)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # BaseTab 末尾是 addStretch(1)；替换为「搜索框 + 树」面板占满剩余空间，
        # 与 LogView 文本预览互为补充：LogView 看采样总览，树看完整可导航明细
        root_lay = self.layout()
        stretch_item = root_lay.takeAt(root_lay.count() - 1)
        del stretch_item   # QSpacerItem 由 takeAt 转交所有权

        self._search = QLineEdit(self)
        self._search.setPlaceholderText('过滤：文件名 / 分组（大小写不敏感）')
        self._search.setClearButtonEnabled(True)
        self._tree = MakeMetaTree(self)
        self._tree.plan_double_clicked.connect(self._on_plan_double_clicked)
        self._tree.plan_apply_requested.connect(self._apply_single)
        self._search.textChanged.connect(self._tree.apply_filter)

        panel = QWidget(self)
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(4)
        panel_lay.addWidget(self._search)
        panel_lay.addWidget(self._tree, 1)
        root_lay.addWidget(panel, 1)

    def _build_options_box(self) -> QWidget:
        self._jobs = QSpinBox()
        self._jobs.setRange(0, 32)
        self._jobs.setValue(1)
        self._jobs.setToolTip(
            'plan 阶段并行进程数；1=串行（默认），0=自动 min(cpu, 4)'
        )
        self._sample_per_group = QSpinBox()
        self._sample_per_group.setRange(0, 999)
        self._sample_per_group.setValue(3)
        self._sample_per_group.setToolTip(
            '预览阶段每类差异展示的样本卡数（默认 3；0=全量，不折叠）'
        )
        self._rare_threshold = QSpinBox()
        self._rare_threshold.setRange(0, 999)
        self._rare_threshold.setValue(5)
        self._rare_threshold.setToolTip(
            '出现 ≤ N 次的差异类视为稀有，强制全量渲染（默认 5）'
        )
        box = QGroupBox('选项')
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel('并行 jobs:'))
        lay.addWidget(self._jobs)
        lay.addSpacing(16)
        lay.addWidget(QLabel('每组样本:'))
        lay.addWidget(self._sample_per_group)
        lay.addWidget(QLabel('稀有阈值:'))
        lay.addWidget(self._rare_threshold)
        lay.addStretch(1)
        return box

    def _extra_action_buttons(self) -> list[QPushButton]:
        self._export_btn = QPushButton('导出预览')
        self._export_btn.setToolTip(
            '将本次预览结构化导出（CSV / JSON）便于批量审查'
        )
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        return [self._export_btn]

    def _banner_subtitle(self) -> str:
        return 'CBZ ComicInfo.xml 批量工具'

    def _plan_call(self, target: Any) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans_for_files, (target,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_plans

    def _render_preview(self, plans: list[MakeMetaPlan]) -> None:
        print_make_meta_preview(
            plans,
            sample_per_group=self._sample_per_group.value(),
            rare_threshold=self._rare_threshold.value(),
        )

    def _count_actionable(self, plans: list[MakeMetaPlan]) -> int:
        return sum(1 for p in plans if p.writable and p.changed)

    def _classify_plans(self, plans: list[MakeMetaPlan]) -> dict[str, int]:
        writable = sum(1 for p in plans if p.writable and p.changed)
        unchanged = sum(1 for p in plans if p.writable and not p.changed)
        return {'可写入': writable, '无变化': unchanged,
                '冲突': len(plans) - writable - unchanged}

    # ── 钩子：扫描完成后启用导出 / 填充树；busy 时禁用 ─────────────────
    def _on_scan(self) -> None:
        super()._on_scan()
        # super 校验通过才会把 _plans 置 None；据此清空树，避免老数据残留
        if self._plans is None:
            self._tree.set_plans([])

    def _on_planned(self, plans: list[MakeMetaPlan]) -> None:
        super()._on_planned(plans)
        self._export_btn.setEnabled(bool(self._plans))
        self._tree.set_plans(self._plans or [])

    def _on_plan_double_clicked(self, plan: MakeMetaPlan) -> None:
        dlg = MakeMetaDetailDialog(plan, parent=self)
        # 详情对话框只发意图，写入仍走 _apply_single；成功后关闭对话框
        dlg.apply_requested.connect(
            lambda p, d=dlg: self._apply_single(p, dialog=d)
        )
        dlg.exec()

    # ── 单条执行（共用入口：树右键 + 详情按钮）─────────────────────────
    def _apply_single(self, plan: MakeMetaPlan, *, dialog=None) -> None:
        """对单个 plan 写入 ComicInfo.xml，并局部更新树 / 状态行。

        :param dialog: 若来自详情对话框，成功后调用其 ``accept()`` 关闭。
        """
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.warning(self, '忙', '后台任务运行中，请先取消')
            return
        if not (plan.writable and plan.changed):
            return
        if QMessageBox.question(
            self, '确认',
            f'对单个文件写入 ComicInfo.xml？\n\n{plan.filename}',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        ) != QMessageBox.Yes:
            return

        # 确保写入日志落到本 Tab 的 LogView（sink 线程本地，用户可能切过 Tab）
        set_output(self._sink)
        emit(f'\n▶ 单条写入: {plan.filename}')
        result = apply_plan(plan)
        if result != 'ok':
            QMessageBox.warning(
                self, '写入失败', f'{plan.filename}\n详情见日志',
            )
            return

        # 状态更新：从 plans 列表移除 + 树局部刷新 + 状态行
        if self._plans:
            self._plans = [p for p in self._plans if p is not plan]
        self._tree.remove_plan(plan)
        self._refresh_post_apply_ui()
        if dialog is not None:
            dialog.accept()

    def _refresh_post_apply_ui(self) -> None:
        if not self._plans:
            self._apply_btn.setEnabled(False)
            self._export_btn.setEnabled(False)
            self._status.setText('扫描完成：所有项目已处理')
            return
        n    = self._count_actionable(self._plans)
        cats = self._classify_plans(self._plans)
        parts = ' / '.join(f'{v} {k}' for k, v in cats.items() if v)
        self._status.setText(f'剩余：{len(self._plans)} 项（{parts}）')
        self._apply_btn.setEnabled(n > 0)

    def _on_busy(self, busy: bool) -> None:
        super()._on_busy(busy)
        if busy:
            self._export_btn.setEnabled(False)

    # ── 导出 ──────────────────────────────────────────────────────────
    def _on_export(self) -> None:
        if not self._plans:
            return
        path, sel = QFileDialog.getSaveFileName(
            self, '导出预览', 'make_meta_preview.csv',
            'CSV (*.csv);;JSON (*.json)',
        )
        if not path:
            return
        # Windows 下 QFileDialog 不自动追加后缀，按所选 filter 补
        lp = path.lower()
        if sel.startswith('CSV') and not lp.endswith('.csv'):
            path += '.csv'
        elif sel.startswith('JSON') and not lp.endswith('.json'):
            path += '.json'
        try:
            out = export_plans(self._plans, path)
        except Exception as e:  # noqa: BLE001 — UI 层兜底
            QMessageBox.warning(self, '导出失败', str(e))
            return
        self._status.setText(f'已导出预览到 {out}')

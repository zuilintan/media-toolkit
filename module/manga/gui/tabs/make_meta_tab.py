"""元数据写入 GUI Tab；复用 :mod:`module.manga.workflow.make_meta`。"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSpinBox, QWidget,
)

from module.manga.core.models import MakeMetaPlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.gui.widgets.make_meta_detail import MakeMetaDetailDialog
from module.manga.gui.widgets.make_meta_tree import MakeMetaTree
from module.manga.presentation.export import export_plans
from module.manga.presentation.view import print_make_meta_preview
from module.manga.workflow.make_meta import apply_plans, preview_plans


class MakeMetaTab(BaseTab):
    cmd_name         = 'make_meta'
    apply_btn_text   = '执行'
    confirm_verb     = '执行'
    no_change_msg    = '没有需要写入的文件'
    root_label       = 'CBZ 根目录:'
    root_placeholder = '递归扫描所有 .cbz'

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # BaseTab 末尾是 addStretch(1)；替换为树视图占满剩余空间，
        # 与 LogView 文本预览互为补充：LogView 看采样总览，树看完整可导航明细
        root_lay = self.layout()
        stretch_item = root_lay.takeAt(root_lay.count() - 1)
        del stretch_item   # QSpacerItem 由 takeAt 转交所有权
        self._tree = MakeMetaTree(self)
        self._tree.plan_double_clicked.connect(self._on_plan_double_clicked)
        root_lay.addWidget(self._tree, 1)

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

    def _plan_call(self, root: str) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans, (root,), {'jobs': self._jobs.value()}

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
        MakeMetaDetailDialog(plan, parent=self).exec()

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

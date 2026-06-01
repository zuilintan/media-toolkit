"""四个子命令 Tab 的通用基类 :class:`BaseTab`。

承担共性:

- 装配通用 UI（根目录 / 扫描+执行按钮 / 状态行）
- 后台 ``QThread`` + ``Worker`` 调度（含防 GC、自动清理）
- 扫描 → 预览 → 二次确认 → 写入 → 重置 状态机

子类只提供策略方法（:meth:`BaseTab._plan_call` / :meth:`BaseTab._apply_fn` /
:meth:`BaseTab._render_preview` / :meth:`BaseTab._count_actionable` /
:meth:`BaseTab._build_options_box` 等）。
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
    QWidget,
)

from base.gui.config import get_config
from base.gui.path_picker import PathPicker
from base.gui.qt_sink import QtSink
from base.gui.worker import Worker
from base.console import SEP2, emit, set_output
from module.manga.presentation.view import print_run_banner


def _run_apply(apply_fn: Callable[..., int], plans: list, **kwargs) -> int:
    """:class:`~base.gui.worker.Worker` 入口：吃掉 ``on_progress``（apply 不用），
    透传 ``cancel_token``，调用 ``apply_fn(plans, False, ...)``。"""
    kwargs.pop('on_progress', None)
    return apply_fn(plans, False, **kwargs)


class BaseTab(QWidget):
    """子命令 Tab 通用基类（UI 骨架 + 任务调度 + 状态机）。"""

    busy_changed = Signal(bool)

    # ── 子类必须覆盖的类常量 ───────────────────────────────────────────
    cmd_name:        str = ''          # QSettings key 前缀（snake_case 标识符）
    apply_btn_text:  str = '执行'      # 写入按钮文案
    confirm_verb:    str = '写入'      # QMessageBox 中的动词
    no_change_msg:   str = '没有需要写入的项目'
    root_label:      str = '根目录:'
    root_placeholder: str = '选择或拖入目录...'

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._sink   = QtSink()          # 此 Tab 专属输出通道
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._plans: list[Any] | None = None

        # ── UI 装配 ───────────────────────────────────────────────────
        self._root_picker = PathPicker(
            self.root_label, self.root_placeholder,
            history_key=f'{self.cmd_name}.root',
        )
        dir_box = QGroupBox('目录')
        dir_lay = QVBoxLayout(dir_box)
        dir_lay.addWidget(self._root_picker)

        self._scan_btn  = QPushButton('预览')
        self._scan_btn.setToolTip('预览 [Enter]')
        self._apply_btn = QPushButton(self.apply_btn_text)
        self._apply_btn.setToolTip(f'{self.apply_btn_text} [Ctrl+Enter]')
        self._apply_btn.setEnabled(False)
        self._scan_btn.clicked.connect(self._on_scan)
        self._apply_btn.clicked.connect(self._on_apply)

        self._cancel_btn = QPushButton('取消')
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._on_cancel)

        btn_lay = QHBoxLayout()
        btn_lay.addWidget(self._scan_btn)
        btn_lay.addWidget(self._apply_btn)
        btn_lay.addWidget(self._cancel_btn)
        btn_lay.addStretch(1)

        self._status = QLabel('待扫描')

        root_lay = QVBoxLayout(self)
        root_lay.addWidget(dir_box)
        # 子类的选项组（jobs / smart / quality 等）
        opt_box = self._build_options_box()
        if opt_box is not None:
            root_lay.addWidget(opt_box)
        root_lay.addLayout(btn_lay)
        root_lay.addWidget(self._status)
        root_lay.addStretch(1)

        self.busy_changed.connect(self._on_busy)
        self._load_settings()

    # ── 子类策略钩子 ───────────────────────────────────────────────────
    def _build_options_box(self) -> QWidget | None:
        """返回放在「目录」组下方的选项组（``QGroupBox``）；无可返回 ``None``。"""
        return None

    def _load_settings(self) -> None:
        """从持久化配置恢复控件状态；在 :meth:`_build_options_box` 之后调用。

        基类处理 ``jobs``（所有 Tab 共有）；子类可 ``super()`` 后追加自己的字段。
        """
        if not hasattr(self, '_jobs'):
            return
        cfg = get_config()
        v = cfg.get(f'{self.cmd_name}.jobs')
        if v is not None:
            self._jobs.setValue(int(v))
        self._jobs.valueChanged.connect(
            lambda val: cfg.set(f'{self.cmd_name}.jobs', val)
        )

    def _plan_call(self, root: str) -> tuple[Callable[..., Any], tuple, dict]:
        """返回 ``(plan_fn, args, kwargs)``，:class:`BaseTab` 据此在 worker 线程调用。"""
        raise NotImplementedError

    def _apply_fn(self) -> Callable[[list, bool], int]:
        """返回 apply 函数（签名 ``(plans, dry_run) -> fail``）。"""
        raise NotImplementedError

    def _render_preview(self, plans: list[Any]) -> None:
        """在日志面板渲染预览（调用对应的 ``print_*_preview``）。"""
        raise NotImplementedError

    def _count_actionable(self, plans: list[Any]) -> int:
        """统计可执行项（驱动按钮启用与确认对话框）。"""
        raise NotImplementedError

    def _classify_plans(self, plans: list[Any]) -> dict[str, int]:
        """返回分类统计；子类可覆盖提供更精确的分类。"""
        n = self._count_actionable(plans)
        return {'可执行': n, '无需操作': len(plans) - n}

    def _banner_subtitle(self) -> str:
        """:func:`~module.manga.presentation.view.print_run_banner` 的副标题；
        默认为空，子类可覆盖。"""
        return ''

    # ── 通用回调 ───────────────────────────────────────────────────────
    def _on_scan(self) -> None:
        root = self._root_picker.path()
        if not root:
            QMessageBox.warning(self, '提示', '请先选择根目录')
            return
        if not Path(root).is_dir():
            QMessageBox.warning(self, '提示', f'不是有效目录:\n{root}')
            return

        set_output(self._sink)
        self._plans = None
        self._apply_btn.setEnabled(False)
        self._status.setText('扫描中...')

        print_run_banner(
            self.cmd_name, self._banner_subtitle(), root, mode_apply=False,
        )
        fn, args, kwargs = self._plan_call(root)
        self._run(
            fn, *args, **kwargs,
            on_finished=self._on_planned,
            on_failed=self._on_task_failed,
        )

    def _on_planned(self, plans: list[Any]) -> None:
        plans = [p for p in plans if p is not None]
        self._plans = plans
        if not plans:
            emit('\n  没有需要处理的文件。')
            emit(SEP2)
            self._status.setText('扫描完成：无可处理项')
            return
        self._render_preview(plans)
        n = self._count_actionable(plans)
        emit(SEP2)
        cats = self._classify_plans(plans)
        parts = ' / '.join(
            f'{v} {k}' for k, v in cats.items() if v
        )
        self._status.setText(f'扫描完成：{len(plans)} 项（{parts}）')
        self._apply_btn.setEnabled(n > 0)

    def _on_apply(self) -> None:
        if not self._plans:
            return
        set_output(self._sink)
        n = self._count_actionable(self._plans)
        if not n:
            QMessageBox.information(self, '提示', self.no_change_msg)
            return

        ans = QMessageBox.question(
            self, '确认',
            f'确认对 {n} 个项目{self.confirm_verb}？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ans != QMessageBox.Yes:
            return

        self._actionable_n = n
        self._status.setText('写入中...')
        self._run(
            _run_apply,
            self._apply_fn(),
            self._plans,
            on_finished=self._on_applied,
            on_failed=self._on_task_failed,
        )

    def _on_applied(self, fail: int) -> None:
        ok = self._actionable_n - fail
        self._status.setText(
            f'写入完成：成功 {ok} / 失败 {fail}'
            if fail else f'写入完成：全部成功 ({ok})'
        )
        emit(SEP2)
        self._plans = None
        self._apply_btn.setEnabled(False)

    def _on_task_failed(self, msg: str) -> None:
        self._status.setText('任务失败')
        emit(f'❌ 后台任务异常:\n{msg}')
        emit(SEP2)

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._cancel_btn.setEnabled(False)
            self._status.setText('取消中...')

    def _on_busy(self, busy: bool) -> None:
        self._scan_btn.setEnabled(not busy)
        self._cancel_btn.setVisible(busy)
        self._cancel_btn.setEnabled(busy)
        if busy:
            self._apply_btn.setEnabled(False)

    # ── 后台任务调度 ───────────────────────────────────────────────────
    def _run(
        self,
        fn: Callable[..., Any],
        *args,
        on_finished: Callable[[Any], None] | None = None,
        on_failed:   Callable[[str], None] | None = None,
        **kwargs,
    ) -> bool:
        """启动后台任务。返回 ``False`` 表示已有任务在跑（拒绝并发）。"""
        if self._thread is not None and self._thread.isRunning():
            return False

        self._thread = QThread(self)
        self._worker = Worker(fn, *args, **kwargs)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        def _quit(*_):
            self._thread.quit()
        self._worker.finished.connect(_quit)
        self._worker.failed.connect(_quit)
        if on_finished:
            self._worker.finished.connect(on_finished)
        if on_failed:
            self._worker.failed.connect(on_failed)

        self._worker.progress.connect(
            lambda c, t: self._status.setText(f'{c}/{t}')
        )

        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_done)

        self.busy_changed.emit(True)
        self._thread.start()
        return True

    def _on_thread_done(self) -> None:
        self._thread = None
        self._worker = None
        self.busy_changed.emit(False)

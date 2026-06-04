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
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
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
        input_widget = self._create_input_widget()
        dir_box = QGroupBox(self._input_box_title())
        dir_lay = QVBoxLayout(dir_box)
        dir_lay.addWidget(input_widget)
        # 垂直 Fixed：保证子类若在下方追加 stretch sibling（如 make_meta 的树
        # 面板）时，输入区不被布局压力压扁——四个 Tab 输入区高度始终一致
        dir_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._scan_btn  = QPushButton('预览')
        self._scan_btn.setToolTip('预览 [Enter]')
        self._apply_btn = QPushButton(self.apply_btn_text)
        self._apply_btn.setToolTip(f'{self.apply_btn_text} [Ctrl+Enter]')
        self._apply_btn.setEnabled(False)
        self._apply_btn.setProperty('primary', True)
        self._scan_btn.clicked.connect(self._on_scan)
        self._apply_btn.clicked.connect(self._on_apply)

        self._cancel_btn = QPushButton('取消')
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._on_cancel)

        # 动作按钮放到输入区右侧的纵向列：让出更多横向空间给列表本身
        btn_col = QVBoxLayout()
        btn_col.addWidget(self._scan_btn)
        btn_col.addWidget(self._apply_btn)
        btn_col.addWidget(self._cancel_btn)
        for b in self._extra_action_buttons():
            btn_col.addWidget(b)
        btn_col.addStretch(1)

        input_row = QHBoxLayout()
        input_row.addWidget(dir_box, 1)
        input_row.addLayout(btn_col)

        self._status = QLabel('待扫描')
        self._status.setProperty('muted', True)

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(10, 10, 10, 10)
        root_lay.setSpacing(8)
        root_lay.addLayout(input_row)
        # 子类的选项组（jobs / smart / quality 等）
        opt_box = self._build_options_box()
        if opt_box is not None:
            root_lay.addWidget(opt_box)
        root_lay.addWidget(self._status)
        root_lay.addStretch(1)

        self.busy_changed.connect(self._on_busy)
        self._load_settings()

    # ── 子类策略钩子 ───────────────────────────────────────────────────
    def _input_box_title(self) -> str:
        """「输入」组的标题。"""
        return '输入'

    def _on_inputs_changed(self) -> None:
        """输入控件清空时复位 apply / status；列表式输入 Tab 通用钩子。

        子类有额外清空动作（如 make_meta 的树视图）可 ``super()`` 后追加。
        """
        if not self._has_inputs():
            self._plans = None
            self._apply_btn.setEnabled(False)
            self._status.setText('待扫描')

    def _has_inputs(self) -> bool:
        """是否已有可扫描的输入；子类按自己的 input 控件覆盖。"""
        return True

    def _create_input_widget(self) -> QWidget:
        """返回放入「输入」组的核心控件。

        默认：根目录 :class:`~base.gui.path_picker.PathPicker`（赋给
        :attr:`_root_picker`，供默认 :meth:`_validate_scan_target` 使用）。
        子类可覆盖为多输入项列表等更复杂的控件。
        """
        self._root_picker = PathPicker(
            self.root_label, self.root_placeholder,
            history_key=f'{self.cmd_name}.root',
        )
        return self._root_picker

    def _build_options_box(self) -> QWidget | None:
        """返回放在「目录」组下方的选项组（``QGroupBox``）；无可返回 ``None``。"""
        return None

    def _extra_action_buttons(self) -> list[QPushButton]:
        """子类钩子：在「取消」之后追加的按钮（如 make_meta 的「导出预览」）。

        在 :meth:`__init__` 中尚未跑到子类 ``__init__`` 主体时被调用，因此
        实现里不能依赖子类自己的实例属性；按需 ``self._xxx_btn = QPushButton(...)``
        并 ``return [self._xxx_btn]`` 即可。
        """
        return []

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

    def _plan_call(self, target: Any) -> tuple[Callable[..., Any], tuple, dict]:
        """返回 ``(plan_fn, args, kwargs)``，:class:`BaseTab` 据此在 worker 线程调用。

        ``target`` 来自 :meth:`_validate_scan_target`（默认为根目录字符串）。
        """
        raise NotImplementedError

    def _validate_scan_target(self) -> Any | None:
        """返回 :meth:`_plan_call` 所需输入；校验失败已 emit / 弹窗后返回 ``None``。

        默认：从 :attr:`_root_picker` 取根目录并校验。子类可覆盖处理多输入项 /
        交互式弹窗（如 std_title 的单文件作者推导）。
        """
        root = self._root_picker.path()
        if not root:
            QMessageBox.warning(self, '提示', '请先选择根目录')
            return None
        if not Path(root).is_dir():
            QMessageBox.warning(self, '提示', f'不是有效目录:\n{root}')
            return None
        return root

    def _format_banner_target(self, target: Any) -> object:
        """把 :meth:`_validate_scan_target` 的返回值格式化为 banner 显示对象。

        默认透传（根目录字符串）。子类可覆盖（如 ``f'单文件模式（{n} 个）'``）。
        """
        return target

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
        target = self._validate_scan_target()
        if target is None:
            return

        set_output(self._sink)
        self._plans = None
        self._apply_btn.setEnabled(False)
        self._status.setText('扫描中...')

        print_run_banner(
            self.cmd_name, self._banner_subtitle(),
            self._format_banner_target(target), mode_apply=False,
        )
        fn, args, kwargs = self._plan_call(target)
        self._run(
            fn, *args, **kwargs,
            on_finished=self._on_planned,
            on_failed=self._on_task_failed,
        )

    def _on_planned(self, plans: list[Any]) -> None:
        # sink 是线程本地的，且用户可能已切到别的 Tab：在主线程回调里重新绑定，
        # 保证 emit 落到本 Tab 的 LogView。
        set_output(self._sink)
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
        set_output(self._sink)
        ok = self._actionable_n - fail
        self._status.setText(
            f'写入完成：成功 {ok} / 失败 {fail}'
            if fail else f'写入完成：全部成功 ({ok})'
        )
        emit(SEP2)
        self._plans = None
        self._apply_btn.setEnabled(False)

    def _on_task_failed(self, msg: str) -> None:
        set_output(self._sink)
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

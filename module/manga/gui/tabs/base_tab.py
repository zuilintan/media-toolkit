"""四个子命令 Tab 的通用基类 :class:`BaseTab`。

承担共性:

- 装配通用 UI（输入区 / 选项 + 动作按钮列 / 预览框）
- 后台 ``QThread`` + ``Worker`` 调度（含防 GC、自动清理）
- 扫描 → 预览 → 二次确认 → 写入 → 重置 状态机
- 内嵌预览树（子类提供 :class:`~module.manga.gui.widgets.preview_tree.PreviewTreeBase`
  实例）+ 单条 apply 流程：右键 / 双击 / 详情对话框统一走 :meth:`_apply_single`

子类只提供策略方法（:meth:`BaseTab._plan_call` / :meth:`BaseTab._apply_fn` /
:meth:`BaseTab._render_preview` / :meth:`BaseTab._count_actionable` /
:meth:`BaseTab._build_options_box` / :meth:`BaseTab._create_preview_tree` 等）。
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from base.gui import BUTTON_COL_WIDTH, make_btn_col
from base.gui.config import get_config
from base.gui.path_picker import PathPicker
from base.gui.qt_sink import QtSink
from base.gui.worker import Worker
from base.console import SEP2, emit, set_output
from module.manga.gui.widgets.preview_tree import PreviewTreeBase
from module.manga.presentation.view import print_run_banner


def _run_apply(apply_fn: Callable[..., int], plans: list, **kwargs) -> int:
    """:class:`~base.gui.worker.Worker` 入口：吃掉 ``on_progress``（apply 不用），
    透传 ``cancel_token``，调用 ``apply_fn(plans, False, ...)``。"""
    kwargs.pop('on_progress', None)
    return apply_fn(plans, False, **kwargs)


class BaseTab(QWidget):
    """子命令 Tab 通用基类（UI 骨架 + 任务调度 + 状态机）。"""

    busy_changed   = Signal(bool)
    status_changed = Signal(str)   # 推到 MangaModule 底部状态栏
    #: 自动化管线一段执行完成（成功 / 失败 / 取消）后发出；list 是给下一 Tab 的
    #: 输入路径，空列表表示「不必继续」（无产出 / 失败 / 用户取消）。
    auto_done      = Signal(list)

    # ── 子类必须覆盖的类常量 ───────────────────────────────────────────
    cmd_name:        str = ''          # QSettings key 前缀（snake_case 标识符）
    apply_btn_text:  str = '执行'      # 写入按钮文案
    confirm_verb:    str = '写入'      # QMessageBox 中的动词
    single_verb:     str = '执行'      # 单条 apply confirm 中的动词
    no_change_msg:   str = '没有需要写入的项目'
    root_label:      str = '根目录:'
    root_placeholder: str = '选择或拖入目录...'
    search_placeholder: str = '过滤：文件名 / 分组（大小写不敏感）'

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._sink   = QtSink()          # 此 Tab 专属输出通道
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._plans: list[Any] | None = None
        self._tree:  PreviewTreeBase | None = None
        # 自动化管线状态：_auto_mode=True 期间跳过所有交互式确认；
        # _auto_aborted 记录用户在 auto 期间点了「取消」，让 _on_applied 知道
        # 即使 worker 正常返回也要终止管线。
        # _auto_pending_apply 由 _on_planned 设置，_on_thread_done 收尾后触发
        # _on_apply —— 避免「worker.finished → _on_planned 同步排 apply」与
        # 「thread.quit() async 完成 → _thread 清空」之间的竞态。
        self._auto_mode:          bool = False
        self._auto_aborted:       bool = False
        self._auto_pending_apply: bool = False
        # _auto_snapshot: 启动 apply 时拍下的 plans 副本，供 auto_collect_outputs
        # 读取。绕开「子类 _on_applied 先 input_list.clear() → _on_inputs_changed
        # 把 self._plans 置 None → super 这边读到空」的级联。
        self._auto_snapshot:      list[Any] | None = None

        # ── UI 装配 ───────────────────────────────────────────────────
        input_widget = self._create_input_widget()
        dir_box = QGroupBox(self._input_box_title())
        dir_lay = QVBoxLayout(dir_box)
        dir_lay.addWidget(input_widget)
        # 垂直 Fixed：保证子类若在下方追加 stretch sibling（如预览框）时，
        # 输入区不被布局压力压扁——四个 Tab 输入区高度始终一致
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

        # 输入按钮列：输入控件暴露的「添加 / 移除选中 / 清空」，摆到输入框右侧
        input_btn_col = make_btn_col(
            getattr(input_widget, 'action_buttons', lambda: [])()
        )
        input_row = QHBoxLayout()
        input_row.addWidget(dir_box, 1)
        input_row.addWidget(input_btn_col)

        # 动作按钮列：预览 / 执行 / 取消 (+ 子类扩展)，摆到选项框右侧
        action_btns = [self._scan_btn, self._apply_btn, self._cancel_btn]
        action_btns.extend(self._extra_action_buttons())
        action_btn_col = make_btn_col(action_btns)

        # 状态文本本地存储；不入布局——由 status_changed signal 推到
        # MangaModule 底部状态栏统一展示
        self._status = QLabel('待扫描')

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(10, 10, 10, 10)
        root_lay.setSpacing(8)
        root_lay.addLayout(input_row)
        # 子类的选项组（jobs / smart / quality 等）：与动作按钮并排
        opt_box = self._build_options_box()
        opt_row = QHBoxLayout()
        if opt_box is not None:
            opt_row.addWidget(opt_box, 1)
        else:
            # 无选项框时仍要让按钮列右贴，左侧空出与选项框等宽的伸缩区
            opt_row.addStretch(1)
        opt_row.addWidget(action_btn_col)
        root_lay.addLayout(opt_row)

        # ── 预览框（子类提供 tree 时启用）─────────────────────────────
        # 搜索 + 树 包入 GroupBox，与输入框 / 选项框 / 状态框视觉一致；
        # 右侧空出与按钮列等宽的占位，使预览框右边界与上方各行对齐
        tree = self._create_preview_tree()
        if tree is not None:
            self._tree = tree
            tree.plan_double_clicked.connect(self._on_plan_double_clicked)
            tree.plan_apply_requested.connect(self._apply_single)

            self._search = QLineEdit(self)
            self._search.setPlaceholderText(self.search_placeholder)
            self._search.setClearButtonEnabled(True)
            self._search.textChanged.connect(tree.apply_filter)

            panel_box = QGroupBox('预览', self)
            panel_lay = QVBoxLayout(panel_box)
            panel_lay.setSpacing(4)
            panel_lay.addWidget(self._search)
            panel_lay.addWidget(tree, 1)

            panel_row = QHBoxLayout()
            panel_row.setContentsMargins(0, 0, 0, 0)
            panel_row.addWidget(panel_box, 1)
            spacer = QWidget(self)
            spacer.setFixedWidth(BUTTON_COL_WIDTH)
            panel_row.addWidget(spacer)
            root_lay.addLayout(panel_row, 1)
        else:
            root_lay.addStretch(1)

        self.busy_changed.connect(self._on_busy)
        self._load_settings()

    # ── 状态文本接口 ───────────────────────────────────────────────────
    def _set_status(self, text: str) -> None:
        """更新本 Tab 状态文本，并向 :class:`~module.manga.gui.module.MangaModule`
        底部状态栏推送。"""
        self._status.setText(text)
        self.status_changed.emit(text)

    def status_text(self) -> str:
        """供 :class:`~module.manga.gui.module.MangaModule` 切 Tab 时同步底栏。"""
        return self._status.text()

    # ── 子类策略钩子 ───────────────────────────────────────────────────
    def _input_box_title(self) -> str:
        """「输入」组的标题。"""
        return '输入'

    def _on_inputs_changed(self) -> None:
        """输入控件清空时复位 apply / status / 树；列表式输入 Tab 通用钩子。"""
        if not self._has_inputs():
            self._plans = None
            self._apply_btn.setEnabled(False)
            self._set_status('待扫描')
            if self._tree is not None:
                self._tree.set_plans([])

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

    def _create_preview_tree(self) -> PreviewTreeBase | None:
        """返回预览树实例；为 ``None`` 时不显示预览框（保持 stretch 占位）。"""
        return None

    def _create_detail_dialog(self, plan: Any) -> QDialog | None:
        """双击 plan 时弹出的详情对话框；``None`` 表示不弹（无详情）。"""
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

    def _apply_one(self, plan: Any) -> str:
        """对单个 plan 执行写入；返回 ``'ok'`` / ``'error'``。

        默认抛 ``NotImplementedError``；子类若启用单条 apply（右键 / 详情对话框）
        必须覆盖。
        """
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

    # ── 自动化管线钩子 ─────────────────────────────────────────────────
    # 编排器在 :class:`~module.manga.gui.module.MangaModule` 里，通过
    # :meth:`auto_start` 触发本 Tab 跑「预览 → 写入」全自动流程，完成后通过
    # :attr:`auto_done` 把产出路径吐给下一 Tab 的 :meth:`auto_set_inputs`。
    def auto_set_inputs(self, paths: list[Any]) -> None:
        """编排器调用：把上一 Tab 的产出路径注入本 Tab 输入控件。
        子类必须覆盖（除非是管线起点：起点用 UI 已添加的输入）。"""
        raise NotImplementedError(
            f'{type(self).__name__}.auto_set_inputs 未实现'
        )

    def auto_collect_outputs(self) -> list[Any]:
        """编排器调用（在 :attr:`_plans` 清空之前）：返回本次 apply 产出路径，
        交给下一 Tab。返回空列表则编排器终止管线。"""
        return []

    def auto_start(self) -> None:
        """非交互式启动：sca + apply 全程不弹确认；完成后 emit :attr:`auto_done`。"""
        if self._auto_mode or (self._thread is not None and self._thread.isRunning()):
            self.auto_done.emit([])
            return
        if not self._has_inputs():
            set_output(self._sink)
            emit(f'⚠️ {self.cmd_name}: 无输入，自动化跳过')
            self.auto_done.emit([])
            return
        self._auto_mode    = True
        self._auto_aborted = False
        self._on_scan()

    def _auto_finish(self, outputs: list[Any]) -> None:
        """清状态 + emit。统一出口避免漏清 flag。"""
        self._auto_mode          = False
        self._auto_aborted       = False
        self._auto_pending_apply = False
        self._auto_snapshot      = None
        self.auto_done.emit(outputs)

    # ── 通用回调 ───────────────────────────────────────────────────────
    def _on_scan(self) -> None:
        target = self._validate_scan_target()
        if target is None:
            return

        set_output(self._sink)
        self._plans = None
        self._apply_btn.setEnabled(False)
        if self._tree is not None:
            self._tree.set_plans([])
        self._set_status('扫描中...')

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
            self._set_status('扫描完成：无可处理项')
            if self._tree is not None:
                self._tree.set_plans([])
            if self._auto_mode:
                self._auto_finish([])
            return
        self._render_preview(plans)
        n = self._count_actionable(plans)
        emit(SEP2)
        cats = self._classify_plans(plans)
        parts = ' / '.join(
            f'{v} {k}' for k, v in cats.items() if v
        )
        self._set_status(f'扫描完成：{len(plans)} 项（{parts}）')
        self._apply_btn.setEnabled(n > 0)
        if self._tree is not None:
            self._tree.set_plans(plans)
        # 自动化：预览完毕直接走 apply（无需二次确认），无可执行项则收尾。
        # ── 时序：worker.finished 同时连了 `_quit`（async thread.quit()）和本
        # 槽，此处 _thread 仍在 quit 过程中、isRunning() 可能仍为 True，直接
        # 调 _on_apply 会被 _run 静默拒绝。改为打个 flag，让 _on_thread_done
        # 在线程真清空后再触发 _on_apply。
        if self._auto_mode:
            if self._auto_aborted:
                self._auto_finish([])
            elif n > 0:
                self._auto_pending_apply = True
            else:
                self._auto_finish([])

    def _on_apply(self) -> None:
        if not self._plans:
            return
        set_output(self._sink)
        n = self._count_actionable(self._plans)
        if not n:
            if self._auto_mode:
                self._auto_finish([])
            else:
                QMessageBox.information(self, '提示', self.no_change_msg)
            return

        # 自动化下跳过 Yes/No 确认（已在编排器入口统一确认过）
        if not self._auto_mode:
            ans = QMessageBox.question(
                self, '确认',
                f'确认对 {n} 个项目{self.confirm_verb}？',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ans != QMessageBox.Yes:
                return

        self._actionable_n = n
        # 拍快照：apply 跑完后 _on_applied 时，自动管线靠这份读产物，避免被
        # 子类 _on_applied 中的 input_list.clear() 级联清成 None
        self._auto_snapshot = list(self._plans)
        self._set_status('写入中...')
        self._run(
            _run_apply,
            self._apply_fn(),
            self._plans,
            on_finished=self._on_applied,
            on_failed=self._on_task_failed,
        )

    def _on_applied(self, fail: int) -> None:
        set_output(self._sink)
        # 产物收集走 _auto_snapshot（apply 启动时拍的副本）：下面 clear input
        # 会经 _on_inputs_changed 把 self._plans 置 None，但 snapshot 不受影响
        outputs: list[Any] = []
        if self._auto_mode and not self._auto_aborted:
            try:
                outputs = self.auto_collect_outputs()
            except Exception as e:
                emit(f'⚠️ 自动化产物收集失败: {e}')
                outputs = []
        # 统一清空输入列表：apply 后入参语义已变（pack_pic rmtree 了源、
        # std_title 改了名、make_cover/meta 本批已写入），保留只会误导用户
        # 「还在等待处理」。必须在 _set_status 之前 clear——_on_inputs_changed
        # 会把状态覆写成「待扫描」，随后 _set_status('写入完成…') 才能盖回去。
        input_widget = getattr(self, '_input_list', None)
        if input_widget is not None:
            input_widget.clear()
        ok = self._actionable_n - fail
        self._set_status(
            f'写入完成：成功 {ok} / 失败 {fail}'
            if fail else f'写入完成：全部成功 ({ok})'
        )
        emit(SEP2)
        self._plans = None
        self._apply_btn.setEnabled(False)
        if self._auto_mode:
            self._auto_finish([] if (fail or self._auto_aborted) else outputs)

    def _on_task_failed(self, msg: str) -> None:
        set_output(self._sink)
        self._set_status('任务失败')
        emit(f'❌ 后台任务异常:\n{msg}')
        emit(SEP2)
        if self._auto_mode:
            self._auto_finish([])

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._cancel_btn.setEnabled(False)
            self._set_status('取消中...')
            if self._auto_mode:
                self._auto_aborted = True

    def _on_busy(self, busy: bool) -> None:
        self._scan_btn.setEnabled(not busy)
        self._cancel_btn.setVisible(busy)
        self._cancel_btn.setEnabled(busy)
        if busy:
            self._apply_btn.setEnabled(False)

    # ── 单条 apply（共用入口：树右键 + 详情对话框）─────────────────────
    def _on_plan_double_clicked(self, plan: Any) -> None:
        dlg = self._create_detail_dialog(plan)
        if dlg is None:
            return
        # 详情对话框只发意图，写入仍走 _apply_single；成功后关闭对话框
        if hasattr(dlg, 'apply_requested'):
            dlg.apply_requested.connect(
                lambda p, d=dlg: self._apply_single(p, dialog=d)
            )
        dlg.exec()

    def _apply_single(self, plan: Any, *, dialog: QDialog | None = None) -> None:
        """对单个 plan 写入，并局部更新树 / 状态行。

        :param dialog: 若来自详情对话框，成功后调用其 ``accept()`` 关闭。
        """
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.warning(self, '忙', '后台任务运行中，请先取消')
            return
        if self._tree is not None and not self._tree._is_actionable(plan):
            return

        label = self._tree._plan_label(plan) if self._tree else str(plan)
        if QMessageBox.question(
            self, '确认',
            f'对单个项目{self.single_verb}？\n\n{label}',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        ) != QMessageBox.Yes:
            return

        # 确保写入日志落到本 Tab 的 LogView（sink 线程本地，用户可能切过 Tab）
        set_output(self._sink)
        emit(f'\n▶ 单条{self.single_verb}: {label}')
        result = self._apply_one(plan)
        if result != 'ok':
            QMessageBox.warning(
                self, f'{self.single_verb}失败',
                f'{label}\n详情见日志',
            )
            return

        # 状态更新：从 plans 列表移除 + 树局部刷新 + 状态行
        if self._plans:
            self._plans = [p for p in self._plans if p is not plan]
        if self._tree is not None:
            self._tree.remove_plan(plan)
        self._refresh_post_apply_ui()
        if dialog is not None:
            dialog.accept()

    def _refresh_post_apply_ui(self) -> None:
        """单条 apply 成功后刷新状态行 / 按钮启用；子类可覆盖加自家逻辑。"""
        if not self._plans:
            self._apply_btn.setEnabled(False)
            self._set_status('扫描完成：所有项目已处理')
            return
        n    = self._count_actionable(self._plans)
        cats = self._classify_plans(self._plans)
        parts = ' / '.join(f'{v} {k}' for k, v in cats.items() if v)
        self._set_status(f'剩余：{len(self._plans)} 项（{parts}）')
        self._apply_btn.setEnabled(n > 0)

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
            lambda c, t: self._set_status(f'{c}/{t}')
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
        # 自动化：scan 完成后 _on_planned 排的 apply，必须等线程真清完才能启
        if self._auto_mode and self._auto_pending_apply:
            self._auto_pending_apply = False
            self._on_apply()

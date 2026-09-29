import logging
import re
import shlex
import config
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)
from game_manager import GameManager
from prefix_manager import PrefixManager
from settings_manager import SettingsManager
from system_utils import SystemUtils
from ui.advanced_settings_dialog import AdvancedSettingsDialog
from ui.env_var_manager_dialog import EnvVarManagerDialog
from ui.game_list_item import AddLabelDialog
from ui.prefix_tab import PrefixTab
from ui.savedata_config_dialog import SavedataConfigDialog
from model.game_card import SavedataConfig
from ui.gamepad.game_actions import GamepadGameActions

logger = logging.getLogger(__name__)

class ResponsiveArtworkLabel(QLabel):
    """Render artwork from its source whenever the label itself changes size."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = QPixmap()
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(20)
        self._render_timer.timeout.connect(self._render_source)

    def set_source(self, pixmap):
        self._source = pixmap
        if pixmap.isNull():
            self.clear()
            return
        self._render_source()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._source.isNull():
            self._render_timer.start()

    def sizeHint(self):
        return QSize(0, self.height())

    def minimumSizeHint(self):
        return QSize(0, self.minimumHeight())

    def _render_source(self):
        if self._source.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        width = self.width()
        height = self.height()
        scaled = self._source.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - width) // 2)
        y = max(0, (scaled.height() - height) // 2)
        self.setPixmap(scaled.copy(x, y, width, height))

class ResponsiveGridWidget(QWidget):
    """Reflow child widgets into as many columns as the current width permits."""

    def __init__(self, minimum_cell_width, maximum_columns=None, balance_last_row=False, parent=None):
        super().__init__(parent)
        self.minimum_cell_width = minimum_cell_width
        self.maximum_columns = maximum_columns
        self.balance_last_row = balance_last_row
        self.widgets = []
        self.columns = 1
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)

    def add_widget(self, widget):
        self.widgets.append(widget)
        self._reflow()

    def clear(self):
        for widget in self.widgets:
            self.grid.removeWidget(widget)
            widget.deleteLater()
        self.widgets.clear()

    def _reflow(self):
        widgets = [
            widget for widget in self.widgets
            if not widget.property("responsiveExcluded")
        ]
        if not widgets:
            return
        widest = max(widget.sizeHint().width() for widget in widgets)
        cell_width = max(self.minimum_cell_width, widest + 12)
        spacing = self.grid.horizontalSpacing()
        available = max(cell_width, self.contentsRect().width())
        columns = max(1, (available + spacing) // (cell_width + spacing))
        if self.maximum_columns:
            columns = min(columns, self.maximum_columns)
        columns = min(columns, len(widgets))
        if self.balance_last_row:
            # Avoid layouts such as 4 + 4 + 1. Giving up one column usually
            # produces a much more intentional-looking 3 + 3 + 3 or 5 + 4.
            while columns > 1:
                last_row = len(widgets) % columns
                if not last_row or last_row * 2 > columns:
                    break
                columns -= 1
        if columns == self.columns and self.grid.count() == len(widgets):
            return
        self.columns = columns
        for widget in self.widgets:
            self.grid.removeWidget(widget)
        for index, widget in enumerate(widgets):
            self.grid.addWidget(widget, index // columns, index % columns)
        self.grid.invalidate()
        self.updateGeometry()

    def refresh(self):
        self._reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(self.minimum_cell_width, hint.height())

class CurrentPageStack(QStackedWidget):
    """Only let the active page contribute to the enclosing scroll height."""

    def sizeHint(self):
        current = self.currentWidget()
        return current.sizeHint() if current else super().sizeHint()

    def minimumSizeHint(self):
        current = self.currentWidget()
        return current.minimumSizeHint() if current else super().minimumSizeHint()

    def setCurrentIndex(self, index):
        super().setCurrentIndex(index)
        self.updateGeometry()

class GamepadGameDetail(QWidget):
    """Full game editor shown inside the Games tab stack, never as a modal."""

    back_requested = Signal()
    game_changed = Signal(str)
    reload_requested = Signal(str)

    SECTION_NAMES = (
        "Environment",
        "Upscaling",
        "Advanced",
        "Images",
        "Wine tools",
    )

    def __init__(self, card, backend, parent=None):
        super().__init__(parent)
        self.setObjectName("gamepadGameDetail")
        self.card = card
        self.original_name = card.name
        self.backend = backend
        self.settings = SettingsManager()
        self.actions = GamepadGameActions(self)
        self.actions.changed.connect(self._action_changed)
        self.actions.deleted.connect(self.back_requested.emit)
        self.actions.process_manager.game_started.connect(self._running_state_changed)
        self.actions.process_manager.game_stopped.connect(self._running_state_changed)
        self.prefixes = PrefixManager.get_all_prefixes()
        self.env_checkboxes = {}
        self.wine_only_action_buttons = []
        self._controller_focus_widget = None
        self._section_navigation_pending = False
        self._detail_entry_pending = True
        self._choice_apply = None
        self._choice_return_widget = None
        self._initializing = True
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self._perform_autosave)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.view_stack = CurrentPageStack()
        outer.addWidget(self.view_stack)

        self.detail_page = QWidget()
        root = QVBoxLayout(self.detail_page)
        root.setContentsMargins(28, 20, 28, 18)
        root.setSpacing(14)
        self.view_stack.addWidget(self.detail_page)

        toolbar = QHBoxLayout()
        self.back_button = QPushButton(self.tr("← Back"))
        self.back_button.setObjectName("gamepadBackButton")
        self.back_button.clicked.connect(self._leave_detail)
        self.title = QLabel(card.name)
        self.title.setObjectName("gamepadDetailTitle")
        self.title.setWordWrap(True)
        self.play_button = QPushButton(self.tr("▶ Play"))
        self.play_button.setObjectName("gamepadPlayButton")
        self.play_button.clicked.connect(lambda: self.actions.toggle_game(self.card))
        toolbar.addWidget(self.back_button)
        toolbar.addWidget(self.title, 1)
        toolbar.addWidget(self.play_button)
        root.addLayout(toolbar)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("gamepadDetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QScrollArea.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_content = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(18)
        self.detail_layout.setAlignment(Qt.AlignTop)
        self.detail_scroll.setWidget(self.detail_content)
        root.addWidget(self.detail_scroll, 1)

        self.layout_art = ResponsiveArtworkLabel()
        self.layout_art.setObjectName("gamepadDetailLayoutArt")
        self.layout_art.setAlignment(Qt.AlignCenter)
        self.layout_art.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.layout_art.hide()
        self._layout_pixmap = QPixmap()
        self.detail_layout.addWidget(self.layout_art)

        overview_widget = QWidget()
        overview_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Maximum
        )
        overview = QHBoxLayout(overview_widget)
        overview.setContentsMargins(0, 0, 0, 0)
        overview.setSpacing(24)
        self.cover = QLabel()
        self.cover.setObjectName("gamepadDetailCover")
        self.cover.setFixedSize(220, 330)
        self.cover.setAlignment(Qt.AlignCenter)
        overview.addWidget(self.cover, 0, Qt.AlignTop)

        info = QVBoxLayout()
        fields_box = QGroupBox(self.tr("Game"))
        fields = QFormLayout(fields_box)
        fields.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.name_edit = QLineEdit(card.name)
        self.path_edit = QLineEdit(card.path)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        self.path_browse_button = QPushButton(self.tr("Browse"))
        self.path_browse_button.clicked.connect(self._browse_executable)
        path_row.addWidget(self.path_browse_button)
        # Keep the combo as the data model, but do not expose its arrow-driven
        # editing in controller mode. Prefix choice happens on a dedicated page.
        self.prefix_combo = QComboBox(self.detail_page)
        self.prefix_combo.addItems(self.prefixes.keys())
        self.prefix_combo.setCurrentText(card.prefix)
        self.prefix_combo.currentTextChanged.connect(self._prefix_changed)
        self.prefix_combo.hide()
        prefix_row = QHBoxLayout()
        self.prefix_button = QPushButton(card.prefix)
        self.prefix_button.setObjectName("gamepadPrefixButton")
        self.prefix_button.clicked.connect(self._show_prefix_page)
        prefix_row.addWidget(self.prefix_button, 1)
        self.add_prefix_button = QPushButton(self.tr("Add prefix"))
        self.add_prefix_button.clicked.connect(self._add_prefix)
        prefix_row.addWidget(self.add_prefix_button)
        self.metadata_edit = QLineEdit(card.vndb)
        self.savedata_label = QLabel(self._savedata_summary())
        self.savedata_label.setWordWrap(True)
        savedata_row = QHBoxLayout()
        savedata_row.addWidget(self.savedata_label, 1)
        self.savedata_button = QPushButton(self.tr("Configure"))
        self.savedata_button.clicked.connect(self._configure_savedata)
        savedata_row.addWidget(self.savedata_button)
        self.gdrive_checkbox = QCheckBox(
            self.tr("Sync this game's savedata to Google Drive")
        )
        self.gdrive_checkbox.setChecked(bool(card.gdrive))
        fields.addRow(self.tr("Name:"), self.name_edit)
        fields.addRow(self.tr("Path:"), path_row)
        fields.addRow(self.tr("Prefix:"), prefix_row)
        fields.addRow(self.tr("VNDB / SGDB:"), self.metadata_edit)
        fields.addRow(self.tr("Savedata:"), savedata_row)
        fields.addRow("", self.gdrive_checkbox)
        info.addWidget(fields_box)

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel(self.tr("Label:")))
        self.label_combo = QComboBox(self.detail_page)
        self._refresh_label_combo(card.label)
        self.label_combo.hide()
        self.label_button = QPushButton()
        self.label_button.setObjectName("gamepadChoiceButton")
        self.label_button.clicked.connect(self._show_label_page)
        self.label_combo.currentIndexChanged.connect(self._update_label_button)
        self._update_label_button()
        label_row.addWidget(self.label_button, 1)
        self.add_label_button = QPushButton(self.tr("Add label"))
        self.add_label_button.clicked.connect(self._add_label)
        label_row.addWidget(self.add_label_button)
        info.addLayout(label_row)
        info.addStretch()
        overview.addLayout(info, 1)
        self.detail_layout.addWidget(overview_widget)

        self.sections = QTabBar()
        self.sections.setObjectName("gamepadDetailSections")
        self.sections.setExpanding(False)
        self.sections.setDrawBase(False)
        self.sections.setFixedHeight(52)
        for name in self.SECTION_NAMES:
            self.sections.addTab(self.tr(name))
        self.sections.currentChanged.connect(self._section_changed)
        self.detail_layout.addWidget(self.sections)

        self.pages = CurrentPageStack()
        self.pages.addWidget(self._build_environment_page())
        self.pages.addWidget(self._build_upscaling_page())

        prefix_type = self._prefix_type()
        self.advanced_engine = AdvancedSettingsDialog(prefix_type, self.card, self)
        self.advanced_engine.hide()
        self.advanced_engine.content_changed.connect(self._schedule_autosave)
        self.pages.addWidget(self._build_advanced_page())
        self.pages.addWidget(self._build_images_page())
        self.pages.addWidget(self._build_wine_page())
        self.pages.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.detail_layout.addWidget(self.pages)

        hints = QLabel(self.tr(
            "B  Back     A  Activate     X  Play/stop     Y  Actions     "
            "L2/R2  Change section     LB/RB  Change tab"
        ))
        hints.setObjectName("gamepadHints")
        hints.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(hints)

        self.actions_page = self._build_actions_page()
        self.view_stack.addWidget(self.actions_page)
        self.prefix_page = self._build_prefix_page()
        self.view_stack.addWidget(self.prefix_page)

        self._load_cover()
        self._load_layout_art()
        self._update_play_button()
        self._refresh_environment()
        self._update_wine_visibility()
        self._connect_autosave_controls()
        self._initializing = False
        self.detail_page.setFocusPolicy(Qt.StrongFocus)
        self.detail_page.setFocus(Qt.OtherFocusReason)

    def _scroll_page(self, content):
        return content

    def _build_actions_page(self):
        page = QWidget()
        page.setObjectName("gamepadActionsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 18)
        layout.setSpacing(18)

        header = QHBoxLayout()
        back = QPushButton(self.tr("← Back to details"))
        back.setObjectName("gamepadBackButton")
        back.clicked.connect(self._hide_actions_page)
        self.actions_title = QLabel(
            self.tr("Actions — {0}").format(self.card.name)
        )
        self.actions_title.setObjectName("gamepadDetailTitle")
        self.actions_title.setWordWrap(True)
        self.actions_title.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        header.addWidget(back)
        header.addWidget(self.actions_title, 1)
        layout.addLayout(header)

        self.action_grid = ResponsiveGridWidget(220, maximum_columns=1)
        action_specs = (
            (self.tr("▶ Play"), lambda: self.actions.toggle_game(self.card), "play"),
            (self.tr("Show logs"), lambda: self.actions.show_logs(self.card), ""),
            (self.tr("Browse files"), lambda: self.actions.browse_files(self.card), ""),
            (self.tr("Open texthooker"), lambda: self.actions.open_texthooker(self.card), "wine"),
            (self.tr("Desktop shortcut"), lambda: self.actions.desktop_shortcut(self.card), ""),
            (self.tr("Steam shortcut"), lambda: self.actions.steam_shortcut(self.card), ""),
            (self.tr("Export"), lambda: self.actions.export(self.card), ""),
            (self.tr("Duplicate"), lambda: self.actions.duplicate(self.card), ""),
            (self.tr("Delete"), lambda: self.actions.delete(self.card), "delete"),
        )
        self.actions_play_button = None
        self.action_buttons = []
        self.selected_action_index = 0
        for text, callback, kind in action_specs:
            button = QPushButton(text)
            button.setFocusPolicy(Qt.StrongFocus)
            button.setMinimumHeight(58)
            button.setProperty("gamepadAction", True)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            button.clicked.connect(callback)
            if kind == "play":
                self.actions_play_button = button
                button.setProperty("gamepadPlayAction", True)
            elif kind == "wine":
                self.wine_only_action_buttons.append(button)
            elif kind == "delete":
                button.setObjectName("gamepadDeleteButton")
            self.action_buttons.append(button)
            self.action_grid.add_widget(button)
        self.actions_scroll = QScrollArea()
        self.actions_scroll.setObjectName("gamepadActionsScroll")
        self.actions_scroll.setWidgetResizable(True)
        self.actions_scroll.setFrameShape(QScrollArea.NoFrame)
        self.actions_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        actions_content = QWidget()
        actions_layout = QVBoxLayout(actions_content)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.addWidget(self.action_grid)
        actions_layout.addStretch()
        self.actions_scroll.setWidget(actions_content)
        layout.addWidget(self.actions_scroll, 1)

        hints = QLabel(self.tr(
            "B  Back to details     A  Activate     X  Play/stop     "
            "Y  Back to details     LB/RB  Change tab"
        ))
        hints.setObjectName("gamepadHints")
        hints.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(hints)
        self.actions_back_button = back
        return page

    def _build_prefix_page(self):
        page = QWidget()
        page.setObjectName("gamepadPrefixPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 18)
        layout.setSpacing(18)

        header = QHBoxLayout()
        back = QPushButton(self.tr("← Back to details"))
        back.setObjectName("gamepadBackButton")
        back.clicked.connect(self._hide_prefix_page)
        self.choice_title = QLabel(self.tr("Choose prefix"))
        self.choice_title.setObjectName("gamepadDetailTitle")
        header.addWidget(back)
        header.addWidget(self.choice_title, 1)
        layout.addLayout(header)

        self.prefix_list = QListWidget()
        self.prefix_list.setObjectName("gamepadPrefixList")
        self.prefix_list.setSpacing(6)
        self.prefix_list.itemActivated.connect(self._select_choice_item)
        layout.addWidget(self.prefix_list, 1)

        hints = QLabel(self.tr(
            "B  Back to details     A  Choose     "
            "X  Play/stop     LB/RB  Change tab"
        ))
        hints.setObjectName("gamepadHints")
        hints.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(hints)
        self.prefix_back_button = back
        return page

    def _show_choice_page(
        self, title, options, current_value, apply_callback, return_widget
    ):
        self.choice_title.setText(title)
        self.prefix_list.clear()
        selected_row = 0
        for row, (label, value) in enumerate(options):
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, value)
            self.prefix_list.addItem(item)
            if value == current_value:
                selected_row = row
        if self.prefix_list.count():
            self.prefix_list.setCurrentRow(selected_row)
        self._choice_apply = apply_callback
        self._choice_return_widget = return_widget
        self.view_stack.setCurrentWidget(self.prefix_page)
        self.prefix_list.setFocus(Qt.OtherFocusReason)
        self._mark_controller_focus(self.prefix_list)

    def _show_prefix_page(self):
        self._show_choice_page(
            self.tr("Choose prefix"),
            [(name, name) for name in self.prefixes],
            self.prefix_combo.currentText(),
            self._apply_prefix_choice,
            self.prefix_button,
        )

    def _apply_prefix_choice(self, value):
        self.prefix_combo.setCurrentText(value)

    def _show_label_page(self):
        self._show_choice_page(
            self.tr("Choose label"),
            [
                (self.label_combo.itemText(index), self.label_combo.itemData(index))
                for index in range(self.label_combo.count())
            ],
            self.label_combo.currentData(),
            self._apply_label_choice,
            self.label_button,
        )

    def _apply_label_choice(self, value):
        index = self.label_combo.findData(value)
        if index >= 0:
            self.label_combo.setCurrentIndex(index)

    def _show_upscaler_profile_page(self):
        self._show_choice_page(
            self.tr("Choose upscaler profile"),
            [
                (
                    self.upscaler_profile.itemText(index),
                    self.upscaler_profile.itemData(index),
                )
                for index in range(self.upscaler_profile.count())
            ],
            self.upscaler_profile.currentData(),
            self._apply_upscaler_profile_choice,
            self.upscaler_profile_button,
        )

    def _apply_upscaler_profile_choice(self, value):
        index = self.upscaler_profile.findData(value)
        if index >= 0:
            self.upscaler_profile.setCurrentIndex(index)

    def _update_label_button(self, *_args):
        button = getattr(self, "label_button", None)
        if button is not None:
            button.setText(self.label_combo.currentText())

    def _update_upscaler_profile_button(self, *_args):
        button = getattr(self, "upscaler_profile_button", None)
        if button is not None:
            button.setText(self.upscaler_profile.currentText())

    def _hide_prefix_page(self):
        self.view_stack.setCurrentWidget(self.detail_page)
        target = self._choice_return_widget or self.prefix_button
        target.setFocus(Qt.OtherFocusReason)
        self._mark_controller_focus(target)
        self._choice_apply = None
        self._choice_return_widget = None

    def _select_choice_item(self, item=None):
        item = item or self.prefix_list.currentItem()
        if item is None:
            return
        callback = self._choice_apply
        value = item.data(Qt.UserRole)
        if callback is not None:
            callback(value)
        self._hide_prefix_page()

    def _refresh_prefix_list(self):
        """Compatibility helper for prefix creation while a chooser is open."""
        if (
            hasattr(self, "prefix_list")
            and self.view_stack.currentWidget() is self.prefix_page
        ):
            self._show_prefix_page()

    def _show_actions_page(self):
        self._update_play_button()
        self.view_stack.setCurrentWidget(self.actions_page)
        QTimer.singleShot(0, self._finish_showing_actions)

    def _finish_showing_actions(self):
        self.action_grid.refresh()
        self.actions_page.updateGeometry()
        self.view_stack.updateGeometry()
        self.selected_action_index = 0
        self._focus_action_button()

    def _visible_action_buttons(self):
        return [
            button for button in self.action_buttons
            if not button.property("responsiveExcluded")
        ]

    def _focus_action_button(self, delta=0):
        buttons = self._visible_action_buttons()
        if not buttons:
            self.actions_back_button.setFocus(Qt.OtherFocusReason)
            return
        focus = QApplication.focusWidget()
        if focus in buttons:
            self.selected_action_index = buttons.index(focus)
        self.selected_action_index = (
            self.selected_action_index + delta
        ) % len(buttons)
        button = buttons[self.selected_action_index]
        button.setFocus(Qt.OtherFocusReason)
        self._mark_controller_focus(button)
        self.actions_scroll.ensureWidgetVisible(button, 20, 20)

    def _hide_actions_page(self):
        self.view_stack.setCurrentWidget(self.detail_page)
        self.sections.setFocus(Qt.OtherFocusReason)
        self._mark_controller_focus(self.sections)

    def _connect_autosave_controls(self):
        controls = (
            (QLineEdit, "textChanged"),
            (QComboBox, "currentIndexChanged"),
            (QCheckBox, "toggled"),
            (QSpinBox, "valueChanged"),
        )
        for widget_type, signal_name in controls:
            for widget in self.detail_page.findChildren(widget_type):
                if widget.property("gamepadAutosaveConnected"):
                    continue
                getattr(widget, signal_name).connect(self._schedule_autosave)
                widget.setProperty("gamepadAutosaveConnected", True)

    def _schedule_autosave(self, *_args):
        if not self._initializing:
            self._autosave_timer.start()

    def _flush_autosave(self):
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
            self._perform_autosave()

    def _leave_detail(self):
        self._flush_autosave()
        self.back_requested.emit()

    def _build_environment_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignTop)
        self.environment_box = QGroupBox(self.tr("Environment Variables"))
        self.environment_layout = QVBoxLayout(self.environment_box)
        self.environment_grid = ResponsiveGridWidget(280, maximum_columns=4)
        self.environment_layout.addWidget(self.environment_grid)
        layout.addWidget(self.environment_box)
        manage = QPushButton(self.tr("Manage Environment Variables"))
        manage.clicked.connect(self._manage_environment)
        layout.addWidget(manage)
        layout.addStretch()
        return self._scroll_page(content)

    def _build_upscaling_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignTop)
        box = QGroupBox(self.tr("Gamescope and upscaling"))
        form = QFormLayout(box)
        self.gamescope_enabled = QCheckBox(self.tr("Enable Gamescope"))
        self.gamescope_enabled.setChecked(self.card.gamescope.enabled == "true")
        self.gamescope_params = QLineEdit(self.card.gamescope.parameters)
        self.upscaler_enabled = QCheckBox(self.tr("Enable linux-rt-upscaler"))
        self.upscaler_enabled.setChecked(self.card.rtUpscaler.enabled == "true")
        self.upscaler_params = QLineEdit(self.card.rtUpscaler.parameters)
        self.upscaler_params.setPlaceholderText("--profile 1080p --crop-top 19")
        parsed_profile, parsed_crop = self._parse_common_upscaler_options(self.card.rtUpscaler.parameters)
        # As with Prefix and Label, keep a hidden combo as the autosaved data
        # model while exposing a controller-friendly full-page chooser.
        self.upscaler_profile = QComboBox(self.detail_page)
        self.upscaler_profile.addItem(self.tr("Automatic / none"), "")
        for profile in self._load_upscaler_profiles(self.card.rtUpscaler.parameters):
            self.upscaler_profile.addItem(profile, profile)

        if parsed_profile and self.upscaler_profile.findData(parsed_profile) < 0:
            self.upscaler_profile.addItem(parsed_profile, parsed_profile)

        self.upscaler_profile.setCurrentIndex(max(0, self.upscaler_profile.findData(parsed_profile)))
        self.upscaler_profile.hide()
        self.upscaler_profile_button = QPushButton()
        self.upscaler_profile_button.setObjectName("gamepadChoiceButton")
        self.upscaler_profile_button.clicked.connect(self._show_upscaler_profile_page)
        self._update_upscaler_profile_button()
        self.upscaler_crop_top = QSpinBox()
        self.upscaler_crop_top.setRange(0, 10000)
        self.upscaler_crop_top.setSpecialValueText(self.tr("None"))
        self.upscaler_crop_top.setSuffix(" px")
        self.upscaler_crop_top.setValue(parsed_crop)
        self.upscaler_profile.currentIndexChanged.connect(self._sync_common_upscaler_options)
        self.upscaler_profile.currentIndexChanged.connect(self._update_upscaler_profile_button)
        self.upscaler_crop_top.valueChanged.connect(self._sync_common_upscaler_options)

        if not config.GAMESCOPE_INSTALLED:
            self.gamescope_enabled.setEnabled(False)
            self.gamescope_params.setEnabled(False)
            
        upscaler_available = self.settings.get(config.USER_CONF_RT_UPSCALER_ENABLED, False)
        self.upscaler_enabled.setVisible(upscaler_available)
        self.upscaler_profile_button.setVisible(upscaler_available)
        self.upscaler_crop_top.setVisible(upscaler_available)
        self.upscaler_params.setVisible(upscaler_available)
        form.addRow(self.gamescope_enabled)
        form.addRow(self.tr("Gamescope parameters:"), self.gamescope_params)
        form.addRow(self.upscaler_enabled)
        form.addRow(self.tr("Profile:"), self.upscaler_profile_button)
        form.addRow(self.tr("Crop top:"), self.upscaler_crop_top)
        form.addRow(self.tr("Upscaler parameters:"), self.upscaler_params)
        layout.addWidget(box)
        layout.addStretch()
        return self._scroll_page(content)

    @staticmethod
    def _upscaler_tokens(parameters):
        try:
            return shlex.split(parameters)
        except ValueError:
            return parameters.split()

    @classmethod
    def _parse_common_upscaler_options(cls, parameters):
        tokens = cls._upscaler_tokens(parameters)
        profile = ""
        crop_top = 0
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in ("-p", "--profile") and index + 1 < len(tokens):
                profile = tokens[index + 1]
                index += 2
                continue
            if token.startswith("--profile="):
                profile = token.partition("=")[2]
            elif token == "--crop-top" and index + 1 < len(tokens):
                try:
                    crop_top = max(0, int(tokens[index + 1]))
                except ValueError:
                    crop_top = 0
                index += 2
                continue
            elif token.startswith("--crop-top="):
                try:
                    crop_top = max(0, int(token.partition("=")[2]))
                except ValueError:
                    crop_top = 0
            index += 1
        return profile, crop_top

    @classmethod
    def _upscaler_config_path(cls, parameters):
        tokens = cls._upscaler_tokens(parameters)
        for index, token in enumerate(tokens):
            if token in ("-c", "--config") and index + 1 < len(tokens):
                return Path(tokens[index + 1]).expanduser()
            if token.startswith("--config="):
                return Path(token.partition("=")[2]).expanduser()
        return Path.home() / ".config" / "linux-rt-upscaler" / "config.yaml"

    @classmethod
    def _load_upscaler_profiles(cls, parameters):
        """Read first-level keys below ``profiles:`` without requiring PyYAML."""
        config_path = cls._upscaler_config_path(parameters)
        try:
            lines = config_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        in_profiles = False
        profile_indent = None
        profiles = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if not in_profiles:
                if re.match(r"^profiles\s*:\s*(?:#.*)?$", stripped):
                    in_profiles = True
                continue
            if indent == 0:
                break
            match = re.match(r"^([^:#][^:]*)\s*:\s*(?:#.*)?$", stripped)
            if not match:
                continue
            if profile_indent is None:
                profile_indent = indent
            if indent != profile_indent:
                continue
            name = match.group(1).strip().strip("'\"")
            if name and name not in profiles:
                profiles.append(name)
        return profiles

    def _compose_upscaler_parameters(self):
        tokens = self._upscaler_tokens(self.upscaler_params.text())
        filtered = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in ("-p", "--profile", "--crop-top"):
                index += 2 if index + 1 < len(tokens) else 1
                continue
            if token.startswith("--profile=") or token.startswith("--crop-top="):
                index += 1
                continue
            filtered.append(token)
            index += 1
        profile = self.upscaler_profile.currentData() or ""
        if profile:
            filtered.extend(("--profile", profile))
        crop_top = self.upscaler_crop_top.value()
        if crop_top:
            filtered.extend(("--crop-top", str(crop_top)))
        return shlex.join(filtered)

    def _sync_common_upscaler_options(self, _value=None):
        self.upscaler_params.setText(self._compose_upscaler_parameters())

    def _build_advanced_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        box = QGroupBox(self.tr("Advanced launch options"))
        form = QFormLayout(box)
        engine = self.advanced_engine
        form.addRow(engine.label_umu_store, engine.edit_umu_store)
        form.addRow(engine.label_umu_id, engine.edit_umu_id)
        form.addRow(self.tr("Pre-Launch Command:"), engine.edit_pre_args)
        form.addRow(self.tr("Game Arguments:"), engine.edit_arguments)
        pre_script_row = QHBoxLayout()
        pre_script_row.addWidget(engine.edit_pre_script)
        pre_script_row.addWidget(engine.btn_pre_script)
        form.addRow(self.tr("Pre-Launch Script:"), pre_script_row)
        form.addRow("", engine.chk_pre_script_wait)
        exit_script_row = QHBoxLayout()
        exit_script_row.addWidget(engine.edit_exit_script)
        exit_script_row.addWidget(engine.btn_exit_script)
        form.addRow(self.tr("Exit Script:"), exit_script_row)
        registry_row = QHBoxLayout()
        registry_row.addWidget(engine.edit_registry_path)
        registry_row.addWidget(engine.btn_detect_registry)
        registry_row.addWidget(engine.btn_copy_registry)
        form.addRow(self.tr("Registry Path:"), registry_row)
        layout.addWidget(box)
        layout.addStretch()
        return self._scroll_page(content)

    def _build_images_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        engine = self.advanced_engine
        layout.addWidget(engine.lbl_vndb_instructions)
        layout.addWidget(engine.current_assets_box)
        layout.addWidget(engine.vndb_group)
        layout.addWidget(engine.sgdb_group)
        layout.addStretch()
        return self._scroll_page(content)

    def _build_wine_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignTop)
        self.wine_box = QGroupBox(self.tr("Wine features"))
        tools_layout = QVBoxLayout(self.wine_box)
        tools = (
            (self.tr("Open Regedit"), "regedit"),
            (self.tr("Open Winecfg"), "winecfg"),
            (self.tr("Open Winefile"), "winefile"),
            (self.tr("Open Windows cmd"), "wineconsole"),
        )
        for index, (text, command) in enumerate(tools):
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, cmd=command: self.actions.run_wine_utility(self.card, cmd))
            tools_layout.addWidget(button)

        bash = QPushButton(self.tr("Open Bash Terminal"))
        bash.clicked.connect(lambda: self.actions.open_bash(self.card))
        tools_layout.addWidget(bash)
        self.wine_unavailable = QLabel(self.tr("Wine tools are unavailable for this emulator entry."))
        self.wine_unavailable.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.wine_box)
        layout.addWidget(self.wine_unavailable)
        layout.addStretch()
        return self._scroll_page(content)

    def _load_cover(self):
        path = SystemUtils.get_cover_path(self.card.cover_path, self.card.vndb)
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            self.cover.setText(self.tr("No cover"))
            return
        scaled = pixmap.scaled(self.cover.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - self.cover.width()) // 2)
        y = max(0, (scaled.height() - self.cover.height()) // 2)
        self.cover.setPixmap(scaled.copy(x, y, self.cover.width(), self.cover.height()))

    def _load_layout_art(self):
        path = Path(self.card.layout_path).expanduser() if self.card.layout_path else None
        pixmap = QPixmap(str(path)) if path and path.is_file() else QPixmap()
        if pixmap.isNull():
            self._layout_pixmap = QPixmap()
            self.layout_art.set_source(QPixmap())
            self.layout_art.hide()
            return
        self._layout_pixmap = pixmap
        self.layout_art.set_source(pixmap)
        self.layout_art.show()
        QTimer.singleShot(0, self._update_layout_art_geometry)

    def _update_layout_art_geometry(self):
        if self._layout_pixmap.isNull() or self.layout_art.isHidden():
            return
        width = max(1, self.detail_scroll.viewport().width())
        aspect_height = round(width * self._layout_pixmap.height() / self._layout_pixmap.width())
        height = max(140, min(320, aspect_height))
        self.layout_art.setFixedHeight(height)

    def _prefix_type(self):
        return self.prefixes.get(self.prefix_combo.currentText(), {}).get("type", "wine")

    def _prefix_changed(self, _name):
        prefix_button = getattr(self, "prefix_button", None)
        if prefix_button:
            prefix_button.setText(self.prefix_combo.currentText())
        self._refresh_environment()
        self._update_wine_visibility()
        is_proton = self._prefix_type() == "proton"
        for widget in (
            self.advanced_engine.label_umu_store,
            self.advanced_engine.label_umu_id,
            self.advanced_engine.edit_umu_store,
            self.advanced_engine.edit_umu_id,
        ):
            widget.setVisible(is_proton)

    def _refresh_environment(self, active_vars=None):
        active_vars = self.card.envvar if active_vars is None else active_vars
        self.environment_grid.clear()
        self.env_checkboxes.clear()
        definitions = self.settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
        prefix_type = self._prefix_type()
        for definition in definitions:
            required = definition.get("req")
            if required and required != prefix_type:
                continue
            checkbox = QCheckBox(definition.get("name") or definition["id"])
            checkbox.setToolTip(
                f"{definition['key']}={definition['value']}"
            )
            checkbox.setChecked(
                active_vars.get(definition["key"]) == definition["value"]
            )
            checkbox.toggled.connect(self._schedule_autosave)
            checkbox.setProperty("gamepadAutosaveConnected", True)
            self.env_checkboxes[definition["id"]] = checkbox
            self.environment_grid.add_widget(checkbox)

    def _manage_environment(self):
        definitions = self.settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
        current = self._collect_environment(definitions)
        dialog = EnvVarManagerDialog(definitions, self)
        if dialog.exec():
            new_definitions = dialog.get_vars()
            self.settings.set(config.USER_CONF_ENV_VARIABLE_LIST, new_definitions)
            self.settings.set(config.USER_CONF_GLOBAL_VARIABLES, dialog.get_global_states())
            new_keys = [definition["key"] for definition in new_definitions]
            GameManager.cleanup_env_vars(new_keys)
            self.card.envvar = {
                key: value for key, value in current.items() if key in new_keys
            }
            self._refresh_environment(self.card.envvar)
            self._schedule_autosave()

    def _collect_environment(self, definitions=None):
        definitions = definitions or self.settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
        result = {}
        for definition in definitions:
            checkbox = self.env_checkboxes.get(definition["id"])
            if checkbox and checkbox.isChecked():
                result[definition["key"]] = definition["value"]
        return result

    def _update_wine_visibility(self):
        available = self._prefix_type() in ("wine", "proton")
        self.wine_box.setVisible(available)
        self.wine_unavailable.setVisible(not available)
        for button in self.wine_only_action_buttons:
            button.setProperty("responsiveExcluded", not available)
            button.setVisible(available)
        action_grid = getattr(self, "action_grid", None)
        if action_grid:
            action_grid.refresh()

    def _refresh_label_combo(self, selected=""):
        self.label_combo.clear()
        self.label_combo.addItem(self.tr("No label"), "")
        for label in self.settings.get(config.USER_CONF_SAVED_LABELS, []):
            self.label_combo.addItem(label, label)
        index = self.label_combo.findData(selected)
        self.label_combo.setCurrentIndex(max(0, index))
        self._update_label_button()

    def _add_label(self):
        dialog = AddLabelDialog(self)
        if dialog.exec() != dialog.Accepted:
            return
        label = dialog.get_label_name().strip()
        if not label:
            return
        labels = self.settings.get(config.USER_CONF_SAVED_LABELS, [])
        if label not in labels:
            labels.append(label)
            self.settings.set(config.USER_CONF_SAVED_LABELS, labels)
        self._refresh_label_combo(label)

    def _browse_executable(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Select Game Executable"), self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def _add_prefix(self):
        created = PrefixTab.create_new_prefix_flow(self)
        if not created:
            return
        self.prefixes = PrefixManager.get_all_prefixes()
        self.prefix_combo.blockSignals(True)
        self.prefix_combo.clear()
        self.prefix_combo.addItems(self.prefixes.keys())
        self.prefix_combo.setCurrentText(created)
        self.prefix_combo.blockSignals(False)
        self.prefix_button.setText(created)
        self._refresh_prefix_list()
        self._prefix_changed(created)
        self._schedule_autosave()

    def _configure_savedata(self):
        data = self.card.to_dict()
        data["path"] = self.path_edit.text()
        dialog = SavedataConfigDialog(data, self)
        if dialog.exec() != dialog.Accepted:
            return
        self.card.savedata = SavedataConfig.from_dict(dialog.result_config())
        self.card.savedata_path = self.card.savedata.primary_path()
        self.savedata_label.setText(self._savedata_summary())
        self._schedule_autosave()

    def _savedata_summary(self):
        savedata = self.card.savedata
        if savedata.mode == "files":
            return self.tr("{} file groups").format(len(savedata.file_groups))
        excluded = sum(len(folder.excluded) for folder in savedata.folders)
        return self.tr("{} folders ({} excluded)").format(
            len(savedata.folders), excluded
        )

    def _perform_autosave(self):
        if self._initializing:
            return
        name = self.name_edit.text().strip()
        if not name:
            return
        self.card.name = name
        self.card.path = self.path_edit.text().strip()
        self.card.prefix = self.prefix_combo.currentText()
        self.card.vndb = self.metadata_edit.text().strip()
        self.card.gdrive = self.gdrive_checkbox.isChecked()
        self.card.label = self.label_combo.currentData() or ""
        self.card.envvar = self._collect_environment()
        self.card.gamescope.enabled = "true" if self.gamescope_enabled.isChecked() else "false"
        self.card.gamescope.parameters = self.gamescope_params.text()
        self.card.rtUpscaler.enabled = "true" if self.upscaler_enabled.isChecked() else "false"
        self.card.rtUpscaler.parameters = self._compose_upscaler_parameters()
        self.advanced_engine.accept()
        self.advanced_engine._user_modified_combos.clear()
        try:
            GameManager.update_game(self.original_name, self.card.to_dict())
        except RuntimeError:
            logger.exception("Could not autosave game %s", self.original_name)
            return
        self.original_name = self.card.name
        self.title.setText(self.card.name)
        self.actions_title.setText(self.tr("Actions — {0}").format(self.card.name))
        self._load_cover()
        self._load_layout_art()
        self.game_changed.emit(self.card.name)

    def save(self):
        """Compatibility entry point; gamepad editing is autosaved."""
        self._flush_autosave()

    def _action_changed(self):
        self.game_changed.emit(self.card.name)

    def _running_state_changed(self, name):
        if name == self.card.name:
            self._update_play_button()

    def _update_play_button(self):
        running = self.actions.process_manager.is_game_running(self.card.name)
        self.play_button.setText(self.tr("■ Stop") if running else self.tr("▶ Play"))
        if self.actions_play_button:
            self.actions_play_button.setText(self.tr("■ Stop") if running else self.tr("▶ Play"))
        for button in (self.play_button, self.actions_play_button):
            if button is None:
                continue
            button.setProperty("running", running)
            button.style().unpolish(button)
            button.style().polish(button)

    def _section_changed(self, index):
        self.pages.setCurrentIndex(index)
        self.sections.setFocus(Qt.OtherFocusReason)
        self._mark_controller_focus(self.sections)
        self._section_navigation_pending = True
        QTimer.singleShot(0, self._scroll_to_sections)

    def _scroll_to_sections(self):
        scroll_bar = self.detail_scroll.verticalScrollBar()
        scroll_bar.setValue(max(0, self.sections.y() - 10))

    def _change_section(self, delta):
        self._detail_entry_pending = False
        count = self.sections.count()
        self.sections.setCurrentIndex((self.sections.currentIndex() + delta) % count)

    def _focus_first_section_control(self):
        if self.sections.currentIndex() == 0:
            candidates = list(self.env_checkboxes.values())
        else:
            page = self.pages.currentWidget()
            candidates = []
            for widget_type in (
                QCheckBox, QLineEdit, QComboBox, QSpinBox, QPushButton
            ):
                candidates.extend(page.findChildren(widget_type))
            candidates.sort(
                key=lambda widget: (
                    widget.mapTo(page, widget.rect().topLeft()).y(),
                    widget.mapTo(page, widget.rect().topLeft()).x(),
                    isinstance(widget, QPushButton),
                )
            )
        for widget in candidates:
            if widget.isVisible() and widget.isEnabled():
                widget.setFocus(Qt.OtherFocusReason)
                self._mark_controller_focus(widget)
                self._section_navigation_pending = False
                self.detail_scroll.ensureWidgetVisible(widget, 20, 20)
                return True
        return False

    def _focus_detail_widget(self, widget):
        if widget is None or not widget.isVisible() or not widget.isEnabled():
            return False
        widget.setFocus(Qt.OtherFocusReason)
        self._mark_controller_focus(widget)
        self.detail_scroll.ensureWidgetVisible(widget, 20, 20)
        return True

    def _navigate_upper_form(self, action, focus):
        """Navigate form rows vertically and their side actions horizontally."""
        primary = [
            self.name_edit,
            self.path_edit,
            self.prefix_button,
            self.metadata_edit,
            self.gdrive_checkbox,
            self.label_button,
            self.sections,
        ]
        side_for = {
            self.path_edit: self.path_browse_button,
            self.prefix_button: self.add_prefix_button,
            self.metadata_edit: self.savedata_button,
            self.label_button: self.add_label_button,
        }
        primary_for_side = {side: main for main, side in side_for.items()}

        if focus in primary_for_side:
            main = primary_for_side[focus]
            if action in ("navigate_left", "navigate_right"):
                return self._focus_detail_widget(main)
            index = primary.index(main)
            delta = -1 if action == "navigate_up" else 1
            if action in ("navigate_up", "navigate_down"):
                return self._focus_detail_widget(
                    primary[max(0, min(len(primary) - 1, index + delta))]
                )
            return True

        if focus not in primary:
            return False
        if action == "navigate_right" and focus in side_for:
            return self._focus_detail_widget(side_for[focus])
        if action == "navigate_left":
            return True
        if action in ("navigate_up", "navigate_down"):
            index = primary.index(focus)
            if action == "navigate_up" and index == 0:
                return self._focus_detail_widget(self.back_button)
            delta = -1 if action == "navigate_up" else 1
            target_index = max(0, min(len(primary) - 1, index + delta))
            return self._focus_detail_widget(primary[target_index])
        return True

    def _mark_controller_focus(self, widget):
        previous = self._controller_focus_widget
        if previous is widget:
            return
        if previous is not None:
            previous.setProperty("controllerSelected", False)
            previous.style().unpolish(previous)
            previous.style().polish(previous)
        self._controller_focus_widget = widget
        if widget is not None:
            widget.setProperty("controllerSelected", True)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def handle_gamepad_action(self, action):
        showing_actions = self.view_stack.currentWidget() is self.actions_page
        if showing_actions:
            if action in ("back", "secondary_action"):
                self._hide_actions_page()
                return
            if action == "primary_action":
                self.actions.toggle_game(self.card)
                return
            if action.startswith("navigate_"):
                delta = -1 if action in ("navigate_left", "navigate_up") else 1
                self._focus_action_button(delta)
                return
            if action == "accept":
                focus = QApplication.focusWidget()
                buttons = self._visible_action_buttons()
                if isinstance(focus, QPushButton):
                    focus.click()
                elif buttons:
                    buttons[self.selected_action_index].click()
                return
        showing_prefixes = self.view_stack.currentWidget() is self.prefix_page
        if showing_prefixes:
            if action == "back":
                self._hide_prefix_page()
                return
            if action == "primary_action":
                self.actions.toggle_game(self.card)
                return
            if action in ("navigate_up", "navigate_down"):
                count = self.prefix_list.count()
                if count:
                    delta = -1 if action == "navigate_up" else 1
                    self.prefix_list.setCurrentRow(
                        (self.prefix_list.currentRow() + delta) % count
                    )
                return
            if action == "accept":
                self._select_choice_item()
                return
        if action == "back":
            self._leave_detail()
            return
        if action == "previous_section":
            self._change_section(-1)
            return
        if action == "next_section":
            self._change_section(1)
            return
        if action == "primary_action":
            self.actions.toggle_game(self.card)
            return
        if action == "secondary_action":
            self._show_actions_page()
            return
        if action.startswith("navigate_"):
            focus = QApplication.focusWidget() or self._controller_focus_widget
            if action == "navigate_down" and self._detail_entry_pending:
                self._detail_entry_pending = False
                self._focus_detail_widget(self.name_edit)
                return
            self._detail_entry_pending = False
            if (
                action == "navigate_down"
                and (focus is self.sections or self._section_navigation_pending)
            ):
                self._focus_first_section_control()
                return
            self._section_navigation_pending = False
            if self._navigate_upper_form(action, focus):
                return
            if isinstance(focus, QSpinBox):
                deltas = {
                    "navigate_up": 1,
                    "navigate_down": -1,
                    "navigate_left": -10,
                    "navigate_right": 10,
                }
                focus.setValue(focus.value() + deltas[action])
                return
            if isinstance(focus, QComboBox) and action in (
                "navigate_up", "navigate_down"
            ):
                delta = -1 if action == "navigate_up" else 1
                focus.setCurrentIndex(
                    (focus.currentIndex() + delta) % max(1, focus.count())
                )
                return
            backwards = action in ("navigate_left", "navigate_up")
            self.focusNextPrevChild(not backwards)
            focus = QApplication.focusWidget()
            if focus:
                focus.ensurePolished()
                self._mark_controller_focus(focus)
            return
        if action == "accept":
            focus = QApplication.focusWidget() or self._controller_focus_widget
            if isinstance(focus, QPushButton):
                focus.click()
            elif isinstance(focus, QCheckBox):
                focus.toggle()
            elif isinstance(focus, QComboBox):
                focus.setCurrentIndex(
                    (focus.currentIndex() + 1) % max(1, focus.count())
                )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._layout_pixmap.isNull():
            QTimer.singleShot(0, self._update_layout_art_geometry)
        engine = getattr(self, "advanced_engine", None)
        if engine:
            if engine._sgdb_valid_items:
                engine._sgdb_resize_timer.start()
            if engine._vndb_image_paths:
                engine._vndb_resize_timer.start()

    def closeEvent(self, event):
        self._flush_autosave()
        engine = getattr(self, "advanced_engine", None)
        if engine and engine.active_image_worker:
            engine.active_image_worker.cancel()
        super().closeEvent(event)

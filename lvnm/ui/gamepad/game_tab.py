import logging
import config
from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)
from game_manager import GameManager
from prefix_manager import PrefixManager
from settings_manager import SettingsManager
from system_utils import SystemUtils
from timetracker.log_manager import LogManager
from ui.gamepad.game_actions import GamepadGameActions

COVER_PATH_ROLE = int(Qt.UserRole) + 1
logger = logging.getLogger(__name__)

class GameCardDelegate(QStyledItemDelegate):
    """Paint a complete cover/name/prefix card inside one scalable border."""

    def __init__(self, card_size, cover_size, card_gap, geometry_scale, text_scale, parent=None):
        super().__init__(parent)
        self.card_size = card_size
        self.cover_size = cover_size
        self.card_gap = card_gap
        self.geometry_scale = geometry_scale
        self.text_scale = text_scale
        self.cell_size = QSize(
            card_size.width() + card_gap,
            card_size.height() + card_gap,
        )
        self._cover_cache = {}

    def sizeHint(self, option, index):
        return self.cell_size

    def set_cell_width(self, width):
        self.cell_size.setWidth(width)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        selected = bool(option.state & QStyle.State_Selected)
        padding = max(7, round(10 * self.geometry_scale))
        gap = max(4, round(6 * self.geometry_scale))
        card_x = option.rect.x() + ((option.rect.width() - self.card_size.width()) / 2)
        card_y = option.rect.y() + ((option.rect.height() - self.card_size.height()) / 2)
        card_rect = QRectF(
            card_x, card_y,
            self.card_size.width(), self.card_size.height(),
        )

        painter.setBrush(QColor("#332e39") if selected else QColor("#1d1c20"))
        painter.setPen(QPen(
            QColor("#bd8cff") if selected else QColor("#343138"),
            max(2, round(3 * self.geometry_scale))
            if selected else max(1, round(self.geometry_scale)),
        ))
        painter.drawRoundedRect(card_rect, 9 * self.geometry_scale, 9 * self.geometry_scale)

        content_width = card_rect.width() - (padding * 2)
        cover_width = min(self.cover_size.width(), round(content_width))
        cover_height = self.cover_size.height()
        cover_x = card_rect.x() + ((card_rect.width() - cover_width) / 2)
        cover_y = card_rect.y() + padding
        cover_rect = QRectF(cover_x, cover_y, cover_width, cover_height)

        cover_path = index.data(COVER_PATH_ROLE)
        pixmap = self._cover_pixmap(cover_path)
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                round(cover_width), round(cover_height),
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
            )
            source_x = max(0.0, (scaled.width() - cover_width) / 2.0)
            source_y = max(0.0, (scaled.height() - cover_height) / 2.0)
            painter.drawPixmap(
                cover_rect,
                scaled,
                QRectF(source_x, source_y, cover_width, cover_height),
            )

        card = index.data(Qt.UserRole)
        name = card.name if card else ""
        prefix = card.prefix if card else ""
        text_x = card_rect.x() + padding
        text_width = card_rect.width() - (padding * 2)
        name_y = cover_rect.bottom() + gap

        name_font = QFont(option.font)
        name_font.setBold(True)
        name_font.setPointSizeF(name_font.pointSizeF() * self.text_scale)
        painter.setFont(name_font)
        painter.setPen(QColor("#f1edf3"))
        name_metrics = painter.fontMetrics()
        name_text = name_metrics.elidedText(name, Qt.ElideRight, round(text_width))
        painter.drawText(
            QRectF(text_x, name_y, text_width, name_metrics.height()),
            Qt.AlignHCenter | Qt.AlignVCenter,
            name_text,
        )

        prefix_font = QFont(option.font)
        prefix_font.setBold(False)
        prefix_font.setPointSizeF(prefix_font.pointSizeF() * self.text_scale)
        painter.setFont(prefix_font)
        painter.setPen(QColor("#bbb5bf"))
        prefix_metrics = painter.fontMetrics()
        prefix_text = prefix_metrics.elidedText(prefix, Qt.ElideRight, round(text_width))
        painter.drawText(
            QRectF(
                text_x,
                name_y + name_metrics.height(),
                text_width,
                prefix_metrics.height(),
            ),
            Qt.AlignHCenter | Qt.AlignVCenter,
            prefix_text,
        )
        painter.restore()

    def _cover_pixmap(self, cover_path):
        if not cover_path:
            return None
        if cover_path not in self._cover_cache:
            self._cover_cache[cover_path] = QPixmap(cover_path)
        return self._cover_cache[cover_path]

class GamepadLabelSection(QFrame):
    """One full-width label header followed by its own card grid."""

    def __init__(self, owner, label_name, cards, expanded):
        super().__init__(owner.sections_content)
        self.owner = owner
        self.label_name = label_name
        self.cards = cards
        self.columns = 1
        self.setObjectName("gamepadLabelSection")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(6, round(8 * owner.zoom)))
        display_name = label_name or self.tr("Uncategorized")
        self.header = QPushButton()
        self.header.setObjectName("gamepadLabelHeader")
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.clicked.connect(self._header_clicked)
        layout.addWidget(self.header)

        self.game_list = QListWidget()
        self.game_list.setObjectName("gamepadGameGrid")
        self.game_list.setViewMode(QListView.IconMode)
        self.game_list.setMovement(QListView.Static)
        self.game_list.setResizeMode(QListView.Adjust)
        self.game_list.setWrapping(True)
        self.game_list.setUniformItemSizes(True)
        self.game_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.game_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.game_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.game_list.setSpacing(0)
        self.delegate = GameCardDelegate(
            owner.card_size,
            owner.cover_size,
            owner.card_gap,
            owner.card_scale,
            owner.DEFAULT_CARD_SCALE,
            self.game_list,
        )
        self.game_list.setItemDelegate(self.delegate)
        self.game_list.currentRowChanged.connect(self._current_row_changed)
        self.game_list.itemActivated.connect(owner._activate_item)
        self.game_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_list.customContextMenuRequested.connect(lambda position: owner._show_card_context_menu(self, position))
        layout.addWidget(self.game_list)

        for card in cards:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, card)
            cover_path = SystemUtils.get_cover_path(card.cover_path, card.vndb)
            if cover_path:
                item.setData(COVER_PATH_ROLE, cover_path)
            self.game_list.addItem(item)

        self.display_name = display_name
        self.set_expanded(expanded, persist=False)

    def _header_clicked(self, checked):
        self.owner._select_header(self)
        self.set_expanded(checked)

    def set_expanded(self, expanded, persist=True):
        self.header.setChecked(expanded)
        arrow = "▼" if expanded else "▶"
        self.header.setText(f"{arrow}  {self.display_name}  ({len(self.cards)})")
        self.game_list.setVisible(expanded and bool(self.cards))
        if persist:
            self.owner.user_settings.set(f"section_expanded_{self.label_name}", expanded)
        if expanded:
            self.update_geometry()

    def update_geometry(self):
        # Measure the list's raw viewport rather than the enclosing scroll
        # area. The outer vertical scrollbar can appear after section heights
        # are assigned and otherwise steals one card column. Add the existing
        # margins back so repeated reflows use the same stable width.
        margins = self.game_list.viewportMargins()
        available_width = (self.game_list.viewport().width() + margins.left() + margins.right())
        if available_width <= 0:
            return
        minimum_width = self.owner.card_size.width() + self.owner.card_gap
        self.columns = max(1, available_width // minimum_width)
        allowance = 4
        natural_gap = (available_width / self.columns) - self.owner.card_size.width()
        horizontal_gap = min(
            self.owner.card_gap * 1.5,
            max(self.owner.card_gap, natural_gap),
        )
        cell_width = self.owner.card_size.width() + round(horizontal_gap)
        cell_width = min(
            cell_width,
            max(
                self.owner.card_size.width(),
                (available_width - allowance) // self.columns,
            ),
        )
        content_width = cell_width * self.columns
        margin = max(0, (available_width - content_width - allowance) // 2)
        cell_height = self.owner.card_size.height() + self.owner.card_gap
        self.delegate.set_cell_width(cell_width)
        self.game_list.setGridSize(QSize(cell_width, cell_height))
        self.game_list.setViewportMargins(margin, 0, margin, 0)
        rows = (len(self.cards) + self.columns - 1) // self.columns
        self.game_list.setFixedHeight(rows * cell_height + 2 if rows else 0)
        self.game_list.scheduleDelayedItemsLayout()

    def _current_row_changed(self, row):
        if row >= 0:
            self.owner._select_game(self, row)

class GamepadGameTab(QWidget):
    """Controller library with grouped grids and a non-modal detail page."""

    BASE_CARD_SIZE = QSize(190, 290)
    BASE_COVER_SIZE = QSize(150, 220)
    DEFAULT_CARD_SCALE = 1.4
    SORT_OPTIONS = (
        ("Latest Played", "latest"),
        ("Total Playtime", "playtime"),
        ("Prefix", "prefix"),
        ("Name", "name"),
    )

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.setObjectName("gamepadGameTab")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.backend = backend
        self.user_settings = SettingsManager()
        self.zoom = self._read_zoom()
        self.sections = []
        self.selected_section = -1
        self.selected_row = -1
        self.detail = None
        self.actions = GamepadGameActions(self)
        self.actions.changed.connect(self.refresh_active_tab)
        self.actions.process_manager.game_started.connect(self._running_state_changed)
        self.actions.process_manager.game_stopped.connect(self._running_state_changed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.screen_stack = QStackedWidget()
        root.addWidget(self.screen_stack)

        self.library_page = QWidget()
        self.main_layout = QVBoxLayout(self.library_page)
        self.main_layout.setSpacing(round(14 * self.zoom))
        self.screen_stack.addWidget(self.library_page)

        header = QHBoxLayout()
        title = QLabel(self.tr("Games"))
        title.setObjectName("gamepadTitle")
        self.open_selected = QPushButton(self.tr("Edit selected"))
        self.open_selected.setEnabled(False)
        self.open_selected.clicked.connect(lambda: self.open_detail(self.current_card()))
        self.play_selected = QPushButton(self.tr("▶ Play selected"))
        self.play_selected.setEnabled(False)
        self.play_selected.clicked.connect(self._run_selected)
        self.sort_combo = QComboBox()
        for text, value in self.SORT_OPTIONS:
            self.sort_combo.addItem(self.tr(text), value)
        saved_sort = self.user_settings.get(config.USER_CONF_SORT_BY_LIST, "latest")
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(saved_sort)))
        self.sort_combo.currentIndexChanged.connect(self._sort_changed)
        self.connection_label = QLabel()
        self.connection_label.setObjectName("gamepadConnection")
        self.connection_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(title)
        header.addWidget(self.open_selected)
        header.addWidget(self.play_selected)
        header.addStretch()
        header.addWidget(QLabel(self.tr("Sort:")))
        header.addWidget(self.sort_combo)
        header.addWidget(self.connection_label)
        self.main_layout.addLayout(header)

        self.sections_scroll = QScrollArea()
        self.sections_scroll.setObjectName("gamepadSectionsScroll")
        self.sections_scroll.setWidgetResizable(True)
        self.sections_scroll.setFrameShape(QFrame.NoFrame)
        self.sections_content = QWidget()
        self.sections_layout = QVBoxLayout(self.sections_content)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(max(10, round(16 * self.zoom)))
        self.sections_layout.setAlignment(Qt.AlignTop)
        self.sections_scroll.setWidget(self.sections_content)
        self.main_layout.addWidget(self.sections_scroll, 1)

        hints = QLabel(self.tr(
            "A  Open/toggle     X  Play     Y  Change sort     "
            "L2/R2  Jump label     LB/RB  Change tab"
        ))
        hints.setObjectName("gamepadHints")
        hints.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.main_layout.addWidget(hints)

        backend.connection_changed.connect(self._on_connection_changed)
        backend.error_changed.connect(self._on_backend_error)
        self._update_connection_status()
        self._apply_zoom()

    def _read_zoom(self):
        try:
            return max(0.5, float(self.user_settings.get(config.USER_CONF_UI_ZOOM, 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def _scaled_size(self, base_size):
        return QSize(
            max(1, round(base_size.width() * self.card_scale)),
            max(1, round(base_size.height() * self.card_scale)),
        )

    def _apply_zoom(self):
        self.card_scale = self.DEFAULT_CARD_SCALE * self.zoom
        self.card_size = self._scaled_size(self.BASE_CARD_SIZE)
        self.cover_size = self._scaled_size(self.BASE_COVER_SIZE)
        self.card_gap = max(12, round(18 * self.card_scale))
        self.main_layout.setContentsMargins(
            round(32 * self.zoom), round(24 * self.zoom),
            round(32 * self.zoom), round(20 * self.zoom),
        )
        self.main_layout.setSpacing(max(8, round(14 * self.zoom)))

    def _clear_sections(self):
        self.sections.clear()
        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def refresh_active_tab(self):
        if self.screen_stack.currentWidget() is not self.library_page:
            return
        new_zoom = self._read_zoom()
        if new_zoom != self.zoom:
            self.zoom = new_zoom
            self._apply_zoom()

        selected_name = self.current_game_name()
        cards = list(GameManager.list_games().values())
        labels = self.user_settings.get(config.USER_CONF_SAVED_LABELS, [])
        groups = {label: [] for label in labels}
        groups[""] = []
        for card in cards:
            groups[card.label if card.label in groups else ""].append(card)

        log_manager = LogManager()
        sort_value = self.sort_combo.currentData()
        for group_cards in groups.values():
            if sort_value == "name":
                group_cards.sort(key=lambda card: card.name.lower())
            elif sort_value == "prefix":
                group_cards.sort(key=lambda card: (card.prefix.lower(), card.name.lower()))
            elif sort_value == "playtime":
                group_cards.sort(
                    key=lambda card: log_manager.get_total_app_playtime(
                        log_manager.get_log_name_from_path(card)
                    ),
                    reverse=True,
                )
            else:
                group_cards.sort(
                    key=lambda card: card.last_played or "0", reverse=True
                )

        self._clear_sections()
        order = sorted(labels, key=str.lower) + [""]
        show_headers = bool(labels)
        for label in order:
            group_cards = groups.get(label, [])
            if not group_cards and label == "":
                continue
            expanded = self.user_settings.get(
                f"section_expanded_{label}", True
            )
            section = GamepadLabelSection(
                self, label, group_cards, expanded if show_headers else True
            )
            if not show_headers:
                section.header.hide()
            self.sections.append(section)
            self.sections_layout.addWidget(section)

        self.selected_section = -1
        self.selected_row = -1
        self.open_selected.setEnabled(False)
        self.play_selected.setEnabled(False)
        restored = False
        for section_index, section in enumerate(self.sections):
            for row, card in enumerate(section.cards):
                if card.name == selected_name:
                    self._select_game(section, row)
                    restored = True
                    break
            if restored:
                break
        if not restored and self.sections:
            if show_headers:
                self._select_header(self.sections[0])
            elif self.sections[0].cards:
                self._select_game(self.sections[0], 0)
        QTimer.singleShot(0, self._update_section_geometry)

    def _update_section_geometry(self):
        for section in self.sections:
            section.update_geometry()
        # Section heights can make the outer scrollbar appear, reducing every
        # grid by its width. Reflow once more after Qt has applied that change.
        QTimer.singleShot(0, self._stabilize_section_geometry)

    def _stabilize_section_geometry(self):
        for section in self.sections:
            section.update_geometry()

    def _sort_changed(self, _index):
        self.user_settings.set(config.USER_CONF_SORT_BY_LIST, self.sort_combo.currentData())
        self.refresh_active_tab()

    def _select_header(self, section):
        try:
            self.selected_section = self.sections.index(section)
        except ValueError:
            return
        self.selected_row = -1
        self.open_selected.setEnabled(False)
        self.play_selected.setEnabled(False)
        self._update_play_selected()
        for other in self.sections:
            other.game_list.clearSelection()
            self._set_header_selected(other, other is section)
        section.header.setFocus(Qt.OtherFocusReason)
        self.sections_scroll.ensureWidgetVisible(section.header, 20, 20)

    def _select_game(self, section, row):
        if row < 0 or row >= len(section.cards):
            return
        try:
            self.selected_section = self.sections.index(section)
        except ValueError:
            return
        self.selected_row = row
        self.open_selected.setEnabled(True)
        self.play_selected.setEnabled(True)
        self._update_play_selected()
        for other in self.sections:
            self._set_header_selected(other, False)
            if other is not section:
                other.game_list.clearSelection()
        section.game_list.blockSignals(True)
        section.game_list.setCurrentRow(row)
        section.game_list.blockSignals(False)
        section.game_list.setFocus(Qt.OtherFocusReason)
        QTimer.singleShot(0, lambda: self._scroll_to_game(section, row))

    @staticmethod
    def _set_header_selected(section, selected):
        header = section.header
        if header.property("controllerSelected") == selected:
            return
        header.setProperty("controllerSelected", selected)
        header.style().unpolish(header)
        header.style().polish(header)

    def focus_controller(self):
        if self.screen_stack.currentWidget() is self.detail and self.detail:
            self.detail.back_button.setFocus(Qt.OtherFocusReason)
        elif self.selected_row < 0 and 0 <= self.selected_section < len(self.sections):
            self.sections[self.selected_section].header.setFocus(Qt.OtherFocusReason)
        elif 0 <= self.selected_section < len(self.sections):
            self.sections[self.selected_section].game_list.setFocus(Qt.OtherFocusReason)

    def _scroll_to_game(self, section, row):
        if row < 0 or row >= section.game_list.count():
            return
        rect = section.game_list.visualItemRect(section.game_list.item(row))
        point = section.game_list.mapTo(self.sections_content, rect.center())
        self.sections_scroll.ensureVisible(point.x(), point.y(), 30, 40)

    def current_card(self):
        if 0 <= self.selected_section < len(self.sections):
            section = self.sections[self.selected_section]
            if 0 <= self.selected_row < len(section.cards):
                return section.cards[self.selected_row]
        return None

    def current_game_name(self):
        card = self.current_card()
        return card.name if card else ""

    def _activate_item(self, item):
        if item:
            self.open_detail(item.data(Qt.UserRole))

    def _show_card_context_menu(self, section, position):
        """Show mouse-only card actions without changing controller bindings."""
        item = section.game_list.itemAt(position)
        if item is None:
            return
        row = section.game_list.row(item)
        self._select_game(section, row)
        card = item.data(Qt.UserRole)

        menu = QMenu(section.game_list)
        running = self.actions.process_manager.is_game_running(card.name)
        play_action = menu.addAction(self.tr("Stop") if running else self.tr("Play"))
        detail_action = menu.addAction(self.tr("Detail"))
        actions_menu = menu.addMenu(self.tr("Actions"))
        action_callbacks = {}

        def add_action(text, callback):
            action = actions_menu.addAction(text)
            action_callbacks[action] = callback

        add_action(self.tr("Show logs"), lambda: self.actions.show_logs(card))
        add_action(self.tr("Browse files"), lambda: self.actions.browse_files(card))
        if PrefixManager.is_wine_game(card):
            add_action(
                self.tr("Open texthooker"),
                lambda: self.actions.open_texthooker(card),
            )
        actions_menu.addSeparator()
        add_action(
            self.tr("Desktop shortcut"),
            lambda: self.actions.desktop_shortcut(card),
        )
        add_action(
            self.tr("Steam shortcut"),
            lambda: self.actions.steam_shortcut(card),
        )
        add_action(self.tr("Export"), lambda: self.actions.export(card))
        add_action(self.tr("Duplicate"), lambda: self.actions.duplicate(card))
        actions_menu.addSeparator()
        add_action(self.tr("Delete"), lambda: self.actions.delete(card))

        selected = menu.exec(section.game_list.viewport().mapToGlobal(position))
        if selected == play_action:
            self.actions.toggle_game(card)
        elif selected == detail_action:
            self.open_detail(card)
        elif selected in action_callbacks:
            action_callbacks[selected]()

    def open_detail(self, card):
        if not card:
            return
        # The advanced image editors pull in the VNDB/SteamGridDB clients.
        # Keep that work off the application startup path until a game is
        # actually opened.
        from ui.gamepad.game_detail import GamepadGameDetail

        if self.detail is not None:
            self.screen_stack.removeWidget(self.detail)
            self.detail.deleteLater()
        self.detail = GamepadGameDetail(card, self.backend, self)
        self.detail.back_requested.connect(self.close_detail)
        self.detail.game_changed.connect(self._detail_changed)
        self.detail.reload_requested.connect(self._reload_detail)
        self.screen_stack.addWidget(self.detail)
        self.screen_stack.setCurrentWidget(self.detail)

    def close_detail(self):
        name = self.detail.card.name if self.detail else ""
        self.screen_stack.setCurrentWidget(self.library_page)
        self.refresh_active_tab()
        if name:
            for section in self.sections:
                for row, card in enumerate(section.cards):
                    if card.name == name:
                        self._select_game(section, row)
                        return

    def _detail_changed(self, _name):
        pass

    def _reload_detail(self, name):
        card = GameManager.get_game(name)
        if card:
            self.open_detail(card)

    def _run_selected(self):
        card = self.current_card()
        if card:
            self.actions.toggle_game(card)

    def _running_state_changed(self, name):
        card = self.current_card()
        if card and card.name == name:
            self._update_play_selected()

    def _update_play_selected(self):
        card = self.current_card()
        running = bool(card and self.actions.process_manager.is_game_running(card.name))
        self.play_selected.setText(self.tr("■ Stop selected") if running else self.tr("▶ Play selected"))

    def _jump_section(self, delta):
        if not self.sections:
            return
        start = max(0, self.selected_section)
        target = (start + delta) % len(self.sections)
        self._select_header(self.sections[target])

    def _navigate(self, action):
        if not self.sections:
            return
        section = self.sections[max(0, self.selected_section)]
        if self.selected_row < 0:
            if action == "navigate_down" and section.header.isChecked() and section.cards:
                self._select_game(section, 0)
            elif action == "navigate_down" and self.selected_section + 1 < len(self.sections):
                self._select_header(self.sections[self.selected_section + 1])
            elif action == "navigate_up" and self.selected_section > 0:
                previous = self.sections[self.selected_section - 1]
                if previous.header.isChecked() and previous.cards:
                    self._select_game(previous, len(previous.cards) - 1)
                else:
                    self._select_header(previous)
            elif action in ("navigate_left", "navigate_right"):
                self._jump_section(-1 if action == "navigate_left" else 1)
            return

        row = self.selected_row
        columns = section.columns
        if action == "navigate_left":
            target = row - 1
        elif action == "navigate_right":
            target = row + 1
        elif action == "navigate_up":
            target = row - columns
            if target < 0:
                self._select_header(section)
                return
        else:
            target = row + columns
            if target >= len(section.cards):
                next_index = self.selected_section + 1
                if next_index < len(self.sections):
                    self._select_header(self.sections[next_index])
                return
        if 0 <= target < len(section.cards):
            self._select_game(section, target)

    def handle_gamepad_action(self, action: str):
        if self.screen_stack.currentWidget() is self.detail and self.detail:
            self.detail.handle_gamepad_action(action)
            return
        if action.startswith("navigate_"):
            self._navigate(action)
        elif action == "accept":
            if self.selected_row < 0 and 0 <= self.selected_section < len(self.sections):
                section = self.sections[self.selected_section]
                section.set_expanded(not section.header.isChecked())
            else:
                self.open_detail(self.current_card())
        elif action == "primary_action":
            self._run_selected()
        elif action == "secondary_action":
            self.sort_combo.setCurrentIndex((self.sort_combo.currentIndex() + 1) % self.sort_combo.count())
        elif action == "previous_section":
            self._jump_section(-1)
        elif action == "next_section":
            self._jump_section(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_section_geometry)

    def _on_connection_changed(self, _connected, _name):
        self._update_connection_status()

    def _on_backend_error(self, _error):
        self._update_connection_status()

    def _update_connection_status(self):
        if self.backend.connected:
            self.connection_label.setText(self.tr("Controller: {0}").format(self.backend.gamepad_name))
        elif self.backend.error:
            self.connection_label.setText(self.tr("Controller unavailable: {0}").format(self.backend.error))
        else:
            self.connection_label.setText(self.tr("Controller: waiting for connection"))

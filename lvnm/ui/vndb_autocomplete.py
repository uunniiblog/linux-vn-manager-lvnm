import logging
from PySide6.QtWidgets import (
    QLineEdit, QListWidget, QListWidgetItem, QWidget, 
    QVBoxLayout, QHBoxLayout, QLabel, QApplication
)
from PySide6.QtCore import Qt, QTimer, QSize, QEvent, Signal
from PySide6.QtGui import QPixmap
from system_utils import SystemUtils
from vndb_manager import VndbSearchWorker

logger = logging.getLogger(__name__)

class VndbAutocompleteLineEdit(QLineEdit):
    """A custom QLineEdit that automatically searches VNDB and displays a popup list."""
    
    # Emits the full dictionary of the selected VN when a user clicks a result
    vn_selected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State
        self.vndb_cached_search_term = ""
        self.vndb_cached_results = []
        self.vndb_has_more = True 
        self.active_vndb_workers = []

        # Timer setup
        # Wait to pause typing before start searching
        self.vndb_search_timer = QTimer(self)
        self.vndb_search_timer.setSingleShot(True)
        self.vndb_search_timer.timeout.connect(self.execute_vndb_search)

        self.textEdited.connect(self.on_name_changed)

        self.autocomplete_list = AutocompleteList(self)
        # Popup flag keeps it on top of parent windows and auto-closes on outside clicks
        self.autocomplete_list.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        # Prevent the popup from stealing focus from the text field
        self.autocomplete_list.setAttribute(Qt.WA_ShowWithoutActivating)
        self.autocomplete_list.itemPressed.connect(self.on_autocomplete_selected)

        # Global event filters for hiding the popup
        QApplication.instance().installEventFilter(self)
        QApplication.instance().applicationStateChanged.connect(self._on_app_state_changed)

    def on_name_changed(self, new_text):
        min_length = 1 if SystemUtils.contains_japanese(new_text) else 3
        if len(new_text) < min_length:
            self.vndb_search_timer.stop()
            self.autocomplete_list.hide()
            return

        # Check local cache first
        filtered = self.vndb_search_try_local_filter(new_text)
        if filtered is not None:
            self.update_autocomplete_popup(filtered)
            return

        self.vndb_search_timer.start(500)

    def vndb_search_try_local_filter(self, text):
        """Search cache filtered results"""
        if not self.vndb_cached_search_term:
            return None

        text_lower = text.lower()
        cached_lower = self.vndb_cached_search_term.lower()

        # only valid when has_more=False, meaning we already have all results for the cached term. Guaranteed to be a subset.
        if not self.vndb_has_more and text_lower.startswith(cached_lower):
            return [vn for vn in self.vndb_cached_results if text_lower in vn["title"].lower()]

        return None

    def execute_vndb_search(self):
        search_term = self.text()
        filtered = self.vndb_search_try_local_filter(search_term)
        
        # Recheck cache again
        if filtered is not None:
            self.update_autocomplete_popup(filtered)
            return

        # Cancel mid way without crashing
        for worker in self.active_vndb_workers:
            worker.cancel()
        
        self.vndb_cached_search_term = search_term
        
        worker = VndbSearchWorker(search_term)
        worker.results_ready.connect(self.on_search_results_received)
        # Remove once finished
        worker.finished.connect(lambda: self.active_vndb_workers.remove(worker) if worker in self.active_vndb_workers else None)
        self.active_vndb_workers.append(worker)
        worker.start()

    def on_search_results_received(self, term, results, has_more):
        self.vndb_cached_results = results
        self.vndb_cached_search_term = term
        self.vndb_has_more = has_more

        if term == self.text():
            self.update_autocomplete_popup(results)

    def update_autocomplete_popup(self, results):
        if not results:
            self.autocomplete_list.hide()
            return

        self.autocomplete_list.clear()
        for vn in results:
            item = QListWidgetItem(self.autocomplete_list)
            item.setSizeHint(QSize(0, 80))
            item.setData(Qt.UserRole, vn)
            widget = VndbResultWidget(vn)
            self.autocomplete_list.setItemWidget(item, widget)

        target_width = self.width()

        win_height = self.window().height() if self.window() else 600
        if win_height > 800:
            # For sidebar
            target_max_height = win_height // 3
        else:
            # For small dialogs
            target_max_height = win_height // 1.8

        n = self.autocomplete_list.count()
        row_h = self.autocomplete_list.sizeHintForRow(0) if n > 0 else 80
        content_height = n * row_h + (self.autocomplete_list.frameWidth() * 2)
        absolute_min = min(content_height, 164)
        final_height = max(absolute_min, min(content_height, target_max_height))
        
        self.autocomplete_list.setFixedWidth(target_width)
        self.autocomplete_list.setFixedHeight(final_height)

        # Position below the LineEdit
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self.autocomplete_list.move(pos)
        self.autocomplete_list.show()
        self.autocomplete_list.raise_()

    def on_autocomplete_selected(self, item):
        vn_data = item.data(Qt.UserRole)
        self.setText(vn_data['title'])
        self.autocomplete_list.hide()
        
        self.vn_selected.emit(vn_data)

    def eventFilter(self, obj, event):
        """Hide popup on any click outside the list or the line edit"""
        if event.type() == QEvent.MouseButtonPress and self.autocomplete_list.isVisible():
            click_pos = event.globalPos()
            list_geo = self.autocomplete_list.geometry()
            
            if not list_geo.contains(click_pos) and not self.rect().contains(self.mapFromGlobal(click_pos)):
                self.autocomplete_list.hide()
        return super().eventFilter(obj, event)

    def _on_app_state_changed(self, state):
        """Hide popup alt tabbing"""
        if state != Qt.ApplicationActive:
            self.autocomplete_list.hide()

    def keyPressEvent(self, event):
        """Standard keyboard navigation for autocomplete lists."""
        if self.autocomplete_list.isVisible():
            count = self.autocomplete_list.count()
            current_row = self.autocomplete_list.currentRow()

            if event.key() == Qt.Key_Down:
                new_row = (current_row + 1) if current_row < count - 1 else 0
                self.autocomplete_list.setCurrentRow(new_row)
                event.accept()
                return
            
            elif event.key() == Qt.Key_Up:
                new_row = (current_row - 1) if current_row > 0 else count - 1
                self.autocomplete_list.setCurrentRow(new_row)
                event.accept()
                return
                
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
                curr = self.autocomplete_list.currentItem()
                if curr:
                    self.on_autocomplete_selected(curr)
                    event.accept()
                    return

            elif event.key() == Qt.Key_Escape:
                self.autocomplete_list.hide()
                event.accept()
                return

        super().keyPressEvent(event)

class AutocompleteList(QListWidget):
    """Subclassed ListWidget to handle smooth hover highlighting."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Install on viewport so mouse events from child widget VndbResultWidget are intercepted
        self.viewport().installEventFilter(self)
        self.setFocusPolicy(Qt.NoFocus)

        # Disable system hover and add mouseover highlight
        self.setStyleSheet("""
            QListWidget::item:hover {
                background-color: transparent;
            }
            QListWidget::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border: none;
            }
        """)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove:
            # Map from the child widget's local coords to viewport coords for itemAt()
            viewport_pos = self.viewport().mapFromGlobal(
                obj.mapToGlobal(event.pos())
            )
            item = self.itemAt(viewport_pos)
            if item:
                self.setCurrentItem(item)
        return super().eventFilter(obj, event)

class VndbResultWidget(QWidget):
    def __init__(self, vn_data, parent=None):
        super().__init__(parent)
        # Pass all mouse events through to the viewport so hover tracking works
        self.setAttribute(Qt.WA_TransparentForMouseEvents) 
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.NoFocus)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setFixedSize(50, 70)
        self.lbl_thumb.setScaledContents(True)
        if vn_data.get("local_temp_path"):
            self.lbl_thumb.setPixmap(QPixmap(vn_data["local_temp_path"]))
        layout.addWidget(self.lbl_thumb)
        
        text_layout = QVBoxLayout()
        self.lbl_title = QLabel(vn_data.get("title", "Unknown"))
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.lbl_title.setWordWrap(True)
        
        self.lbl_id = QLabel(vn_data.get("id", ""))
        self.lbl_id.setStyleSheet("font-size: 10px;")
        
        text_layout.addWidget(self.lbl_title)
        text_layout.addWidget(self.lbl_id)
        layout.addLayout(text_layout)
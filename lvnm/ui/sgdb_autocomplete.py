import os
import requests
import config
import logging
import concurrent.futures
from PySide6.QtWidgets import (
    QLineEdit, QListWidget, QListWidgetItem, QWidget, 
    QVBoxLayout, QHBoxLayout, QLabel, QApplication, QStyle,
    QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QSize, QEvent, Signal, QThread
from PySide6.QtGui import QPixmap
from steamgrid_manager import SteamGridDbManager, SteamGridDbImagesWorker

logger = logging.getLogger(__name__)

class SgdbAutocompleteLineEdit(QLineEdit):
    """A custom QLineEdit that automatically searches SteamGridDB and displays a popup list."""
    
    # Emits the full dictionary of the selected game when a user clicks a result
    game_selected = Signal(dict)
    # Emits (grids, heroes)
    assets_ready = Signal(list, list)
    # Emits status messages for the UI
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State
        self.sgdb_cached_search_term = ""
        self.sgdb_cached_results = []
        self.active_sgdb_workers = []
        self.active_asset_worker = None #

        # Timer setup
        # Wait to pause typing before start searching
        self.sgdb_search_timer = QTimer(self)
        self.sgdb_search_timer.setSingleShot(True)
        self.sgdb_search_timer.timeout.connect(self.execute_sgdb_search)

        self.textEdited.connect(self.on_name_changed)

        self.autocomplete_list = SgdbAutocompleteList(self)
        # Popup flag keeps it on top of parent windows and auto-closes on outside clicks
        self.autocomplete_list.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        # Prevent the popup from stealing focus from the text field
        self.autocomplete_list.setAttribute(Qt.WA_ShowWithoutActivating)
        self.autocomplete_list.itemPressed.connect(self.on_autocomplete_selected)

        self.loading_action = self.addAction(
            self.style().standardIcon(QStyle.SP_BrowserReload), 
            QLineEdit.TrailingPosition
        )
        self.loading_action.setVisible(False)

        # Global event filters for hiding the popup
        QApplication.instance().installEventFilter(self)
        QApplication.instance().applicationStateChanged.connect(self._on_app_state_changed)

    def on_name_changed(self, new_text):
        if len(new_text) < 3:
            self.sgdb_search_timer.stop()
            self.autocomplete_list.hide()
            return

        # Check local cache first
        filtered = self.sgdb_search_try_local_filter(new_text)
        if filtered is not None:
            self.update_autocomplete_popup(filtered)
            return

        self.sgdb_search_timer.start(500)

    def sgdb_search_try_local_filter(self, text):
        """Search cache filtered results"""
        if not self.sgdb_cached_search_term:
            return None

        text_lower = text.lower()
        cached_lower = self.sgdb_cached_search_term.lower()

        if text_lower.startswith(cached_lower) and self.sgdb_cached_results:
            return [g for g in self.sgdb_cached_results if text_lower in g.get("name", "").lower()]

        return None

    def execute_sgdb_search(self):
        search_term = self.text()
        filtered = self.sgdb_search_try_local_filter(search_term)
        
        # Recheck cache again
        if filtered is not None:
            self.update_autocomplete_popup(filtered)
            return

        if not SteamGridDbManager._get_api_key():
            QMessageBox.critical(
                self.window(),
                "No API Key",
                "No SteamGridDB API key is set.\n\nPlease add your key in Settings."
            )
            return

        # Cancel mid way without crashing
        for worker in self.active_sgdb_workers:
            worker.cancel()
        
        self.sgdb_cached_search_term = search_term

        self.loading_action.setVisible(True)
        worker = SgdbAutocompleteWorker(search_term)
        worker.results_ready.connect(self.on_search_results_received)
        # Remove once finished
        worker.finished.connect(lambda: self.active_sgdb_workers.remove(worker) if worker in self.active_sgdb_workers else None)
        self.active_sgdb_workers.append(worker)
        worker.start()

    def on_search_results_received(self, term, results):
        self.loading_action.setVisible(False)
        self.sgdb_cached_results = results
        self.sgdb_cached_search_term = term

        if term == self.text():
            self.update_autocomplete_popup(results)

    def update_autocomplete_popup(self, results):
        if not results:
            self.autocomplete_list.hide()
            return

        self.autocomplete_list.clear()
        for game in results:
            item = QListWidgetItem(self.autocomplete_list)
            item.setSizeHint(QSize(0, 80))
            item.setData(Qt.UserRole, game)
            widget = SgdbResultWidget(game)
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
        game_data = item.data(Qt.UserRole)
        self.setText(game_data['name'])
        self.autocomplete_list.hide()
        
        self.game_selected.emit(game_data)

        # start fetching grids/heroes
        self.fetch_game_assets(game_data['id'], game_data['name'])

    def fetch_game_assets(self, game_id, game_name: str = ""):
        self.status_changed.emit("Fetching images...")
        
        if self.active_asset_worker:
            self.active_asset_worker.cancel()

        api_key = SteamGridDbManager._get_api_key()
        self.active_asset_worker = SteamGridDbImagesWorker(game_id, game_name, api_key)
        self.active_asset_worker.images_ready.connect(self._on_assets_received)
        self.active_asset_worker.start()

    def _on_assets_received(self, grids, heroes):
        self.status_changed.emit("")
        self.assets_ready.emit(grids, heroes)

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


class SgdbAutocompleteList(QListWidget):
    """Subclassed ListWidget to handle smooth hover highlighting."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewport().installEventFilter(self)
        self.setFocusPolicy(Qt.NoFocus)

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
            viewport_pos = self.viewport().mapFromGlobal(
                obj.mapToGlobal(event.pos())
            )
            item = self.itemAt(viewport_pos)
            if item:
                self.setCurrentItem(item)
        return super().eventFilter(obj, event)


class SgdbResultWidget(QWidget):
    def __init__(self, game_data, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents) 
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.NoFocus)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setFixedSize(50, 70)
        self.lbl_thumb.setScaledContents(True)
        if game_data.get("local_temp_path"):
            self.lbl_thumb.setPixmap(QPixmap(game_data["local_temp_path"]))
        layout.addWidget(self.lbl_thumb)
        
        text_layout = QVBoxLayout()
        self.lbl_title = QLabel(game_data.get("name", "Unknown"))
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.lbl_title.setWordWrap(True)
        
        self.lbl_id = QLabel(str(game_data.get("id", "")))
        self.lbl_id.setStyleSheet("font-size: 10px;")
        
        text_layout.addWidget(self.lbl_title)
        text_layout.addWidget(self.lbl_id)
        layout.addLayout(text_layout)


class SgdbAutocompleteWorker(QThread):
    """Searches SteamGridDB and fetches 1 grid per result to use as a thumbnail."""
    results_ready = Signal(str, list)

    def __init__(self, search_term):
        super().__init__()
        self.search_term = search_term
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        api_key = SteamGridDbManager._get_api_key()
        if not api_key:
            if not self._cancelled:
                self.results_ready.emit(self.search_term, [])
            return

        # Search games natively through SGDB manager
        games = SteamGridDbManager.search_games(self.search_term, api_key)
        if self._cancelled or not games:
            if not self._cancelled:
                self.results_ready.emit(self.search_term, [])
            return

        games = games[:6]

        temp_dir = config.TEMP_COVERS
        temp_dir.mkdir(parents=True, exist_ok=True)
        session = requests.Session()

        def fetch_and_download_grid(game):
            if self._cancelled:
                return game
            
            game_id = game["id"]
            
            # Fetch grids for this game to get a thumbnail
            try:
                grid_url = f"{SteamGridDbManager.SGDB_API_URL}/grids/game/{game_id}"
                
                api_headers = SteamGridDbManager._headers(api_key)
                res = session.get(grid_url, headers=api_headers, timeout=5)
                res.raise_for_status()
                data = res.json()
                
                if data.get("success") and data.get("data"):
                    first_grid = data["data"][0]
                    thumb_url = first_grid.get("thumb") or first_grid.get("url")
                    
                    if thumb_url:
                        ext = os.path.splitext(thumb_url)[1] or ".jpg"
                        target = temp_dir / f"sgdb_thumb_{game_id}{ext}"
                        
                        if target.exists():
                            game["local_temp_path"] = str(target)
                        else:
                            # Fetch the actual image without the API key header
                            img_res = session.get(thumb_url, timeout=5)
                            img_res.raise_for_status()
                            with open(target, 'wb') as f:
                                f.write(img_res.content)
                            game["local_temp_path"] = str(target)
            except Exception as e:
                logger.debug(f"[SGDB Autocomplete] Failed to fetch grid thumb for {game.get('name')}: {e}")
            
            return game

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(fetch_and_download_grid, games))

        if not self._cancelled:
            self.results_ready.emit(self.search_term, results)
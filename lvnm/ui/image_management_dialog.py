import config
from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QGridLayout, QGroupBox, 
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, 
    QTabWidget, QVBoxLayout, QWidget
)
from steamgrid_manager import SteamGridDbManager
from system_utils import SystemUtils
from ui.sgdb_autocomplete import SgdbAutocompleteLineEdit
from ui.vndb_autocomplete import VndbAutocompleteLineEdit
from vndb_manager import VndbReleaseImagesWorker

class ImageManagementDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, current_game, parent=None):
        super().__init__(parent)
        self.current_game = current_game
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)
        self.selected_vndb_id = current_game.vndb
        self.sgdb_game_id = None
        self._candidates = {}
        self._visible_keys = {"vndb": [], "sgdb": []}
        self._roles = {}
        self._changed_roles = set()
        self.image_updates = {}
        self._combos = {}
        self._workers = []

        self.setWindowTitle(f"{self.tr('Manage Images')} — {current_game.name}")
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(900, max(340, available.width() - 60)), min(680, max(420, available.height() - 60)))
        self.setMinimumSize(320, 360)

        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        note = QLabel(self.tr("Choose one vertical cover and one horizontal layout. Changes are saved when you press Save."))
        note.setWordWrap(True)
        outer.addWidget(note)

        current_box = QGroupBox(self.tr("Selected images"))
        current_layout = QHBoxLayout(current_box)
        current_layout.setSpacing(8)
        self.cover_preview = self._make_preview(self.tr("Vertical cover"), 76, 98, 1, current_layout)
        self.layout_preview = self._make_preview(self.tr("Horizontal layout"), 124, 98, 2, current_layout)
        current_layout.addStretch()
        clear_button = QPushButton(self.tr("Clear all"))
        clear_button.setToolTip(self.tr("Remove both selected images"))
        clear_button.clicked.connect(self._clear_images)
        current_layout.addWidget(clear_button, 0, Qt.AlignTop)
        outer.addWidget(current_box)

        self.tabs = QTabWidget()
        self.vndb_page, self.vndb_grid, self.vndb_scroll = self._make_gallery_page(self.tr("Search VNDB releases"))
        self.sgdb_page, self.sgdb_grid, self.sgdb_scroll = self._make_gallery_page(self.tr("Search SteamGridDB games"))
        self.tabs.addTab(self.vndb_page, self.tr("VNDB"))
        self.tabs.addTab(self.sgdb_page, self.tr("SteamGridDB"))
        outer.addWidget(self.tabs, 1)

        self.vndb_search = VndbAutocompleteLineEdit(self)
        self.vndb_search.setPlaceholderText(self.tr("Game name or VNDB ID"))
        self.vndb_search.setText(current_game.name)
        self.vndb_search.vn_selected.connect(self._on_vndb_selected)
        vndb_search_row = QHBoxLayout()
        vndb_search_row.addWidget(self.vndb_search, 1)
        vndb_search_button = QPushButton(self.tr("Search"))
        vndb_search_button.clicked.connect(self.vndb_search.execute_vndb_search)
        vndb_search_row.addWidget(vndb_search_button)
        self.vndb_page.layout().insertLayout(0, vndb_search_row)

        self.sgdb_search = SgdbAutocompleteLineEdit(self)
        self.sgdb_search.setPlaceholderText(self.tr("Game name"))
        self.sgdb_search.setText(current_game.name)
        self.sgdb_search.game_selected.connect(self._on_sgdb_selected)
        self.sgdb_search.assets_ready.connect(self._on_sgdb_images_ready)
        self.sgdb_search.status_changed.connect(lambda message: self._set_status(self.sgdb_page, message))
        sgdb_search_row = QHBoxLayout()
        sgdb_search_row.addWidget(self.sgdb_search, 1)
        sgdb_search_button = QPushButton(self.tr("Search"))
        sgdb_search_button.clicked.connect(self.sgdb_search.execute_sgdb_search)
        sgdb_search_row.addWidget(sgdb_search_button)
        self.sgdb_page.layout().insertLayout(0, sgdb_search_row)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton(self.tr("Cancel"))
        save_button = QPushButton(self.tr("Save"))
        save_button.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        cancel_button.clicked.connect(self.reject)
        save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        outer.addLayout(buttons)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._rebuild_galleries)
        self.vndb_scroll.viewport().installEventFilter(self)
        self.sgdb_scroll.viewport().installEventFilter(self)
        self._update_previews()
        geometry = self.settings.value("ImageManagementDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def showEvent(self, event):
        super().showEvent(event)
        self.vndb_search.setFocus()
        self.vndb_search.selectAll()

    def _make_preview(self, title, width, height, role, layout):
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        caption = QLabel(title)
        caption.setAlignment(Qt.AlignCenter)
        preview = QLabel()
        preview.setFixedSize(width, height)
        preview.setAlignment(Qt.AlignCenter)
        preview.setStyleSheet("border: 1px solid palette(mid); background: palette(base);")
        column.addWidget(caption)
        column.addWidget(preview)
        clear_button = QPushButton(self.tr("Remove"))
        clear_button.clicked.connect(lambda: self._clear_role(role))
        column.addWidget(clear_button)
        layout.addWidget(container, 0, Qt.AlignTop)
        return preview

    def _make_gallery_page(self, placeholder):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        page.status = QLabel(placeholder)
        page.status.setWordWrap(True)
        layout.addWidget(page.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page, grid, scroll

    @staticmethod
    def _set_status(page, message):
        page.status.setText(message)
        page.status.setVisible(bool(message))

    def _on_vndb_selected(self, vn_data):
        game_id = vn_data.get("id")
        if not game_id:
            return
        self.selected_vndb_id = game_id
        self._set_status(self.vndb_page, self.tr("Fetching images..."))
        main_cover = (vn_data.get("image") or {}).get("url")
        for worker in self._workers:
            worker.cancel()
        worker = VndbReleaseImagesWorker(game_id, main_cover)
        worker.setParent(QApplication.instance())
        worker.images_ready.connect(lambda paths, source_id=game_id: self._on_vndb_images_ready(source_id, paths))
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _on_vndb_images_ready(self, game_id, image_paths):
        if game_id != self.selected_vndb_id:
            return
        images = []
        for item in image_paths:
            path = item.get("local_path", "")
            if path and not QPixmap(path).isNull():
                images.append({"key": ("vndb", path), "source": "vndb", "local_path": path, "source_url": item.get("url", ""), "game_id": game_id})
        self._set_gallery("vndb", images)

    def _on_sgdb_selected(self, game_data):
        self.sgdb_game_id = game_data.get("id")
        self._set_status(self.sgdb_page, self.tr("Fetching images..."))

    def _on_sgdb_images_ready(self, grids, heroes):
        images = []
        for item in grids + heroes:
            path = item.get("local_path", "")
            if path and not QPixmap(path).isNull():
                images.append({"key": ("sgdb", item.get("full_url") or path), "source": "sgdb", "local_path": path,
                               "source_url": item.get("full_url", ""), "game_id": self.sgdb_game_id, "item": item})
        self._set_gallery("sgdb", images)

    def _set_gallery(self, source, images):
        self._visible_keys[source] = [image["key"] for image in images]
        for image in images:
            key = image["key"]
            self._candidates[key] = image
            self._roles.setdefault(key, 0)
            role = self._saved_role(image)
            if role and role not in self._changed_roles:
                for other_key, other_role in list(self._roles.items()):
                    if other_role == role:
                        self._roles[other_key] = 0
                        other_combo = self._combos.get(other_key)
                        if other_combo:
                            other_combo.blockSignals(True)
                            other_combo.setCurrentIndex(0)
                            other_combo.blockSignals(False)
                self._roles[key] = role
        page = self.vndb_page if source == "vndb" else self.sgdb_page
        self._set_status(page, "" if images else self.tr("No images found."))
        self._rebuild_gallery(source)
        self._update_previews()

    def _saved_role(self, image):
        source_url = image["source_url"]
        path = image["local_path"]
        if (source_url and source_url == self.current_game.cover_source_url) or SystemUtils.are_files_identical(path, self.current_game.cover_path):
            return 1
        if (source_url and source_url == self.current_game.layout_source_url) or SystemUtils.are_files_identical(path, self.current_game.layout_path):
            return 2
        return 0

    def _rebuild_galleries(self):
        self._rebuild_gallery("vndb")
        self._rebuild_gallery("sgdb")

    def _rebuild_gallery(self, source):
        grid = self.vndb_grid if source == "vndb" else self.sgdb_grid
        scroll = self.vndb_scroll if source == "vndb" else self.sgdb_scroll
        while grid.count():
            item = grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._combos = {key: combo for key, combo in self._combos.items() if key[0] != source}
        width = max(160, scroll.viewport().width() - 20)
        columns = max(1, width // 180)
        for index, key in enumerate(self._visible_keys[source]):
            image = self._candidates[key]
            card = QWidget()
            card.setFixedWidth(164)
            column = QVBoxLayout(card)
            column.setContentsMargins(2, 2, 2, 2)
            column.setSpacing(4)
            thumbnail = QLabel()
            thumbnail.setFixedSize(160, 150)
            thumbnail.setAlignment(Qt.AlignCenter)
            pixmap = QPixmap(image["local_path"])
            thumbnail.setPixmap(pixmap.scaled(156, 146, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            column.addWidget(thumbnail)
            if source == "sgdb":
                details = image["item"]
                metadata = QLabel(f'{details.get("style") or ""} · {details.get("author") or ""}'.strip(" ·"))
                metadata.setWordWrap(True)
                metadata.setAlignment(Qt.AlignCenter)
                metadata.setMaximumHeight(30)
                column.addWidget(metadata)
            combo = QComboBox()
            combo.addItems([self.tr("None"), self.tr("Vertical cover"), self.tr("Horizontal layout")])
            combo.setCurrentIndex(self._roles.get(key, 0))
            combo.setFocusPolicy(Qt.StrongFocus)
            combo.installEventFilter(self)
            combo.currentIndexChanged.connect(lambda role, image_key=key: self._role_changed(image_key, role))
            column.addWidget(combo)
            self._combos[key] = combo
            grid.addWidget(card, index // columns, index % columns)

    def _role_changed(self, key, role):
        old_role = self._roles.get(key, 0)
        if old_role == role:
            return
        if old_role:
            self._changed_roles.add(old_role)
        if role:
            self._changed_roles.add(role)
            for other_key, other_role in list(self._roles.items()):
                if other_key != key and other_role == role:
                    self._roles[other_key] = 0
                    other_combo = self._combos.get(other_key)
                    if other_combo:
                        other_combo.blockSignals(True)
                        other_combo.setCurrentIndex(0)
                        other_combo.blockSignals(False)
        self._roles[key] = role
        self._update_previews()

    def _selected_image(self, role):
        for key, value in self._roles.items():
            if value == role:
                return self._candidates.get(key)
        return None

    def _update_previews(self):
        for role, label, path in ((1, self.cover_preview, self.current_game.cover_path), (2, self.layout_preview, self.current_game.layout_path)):
            selected = self._selected_image(role)
            if selected:
                path = selected["local_path"]
            elif role in self._changed_roles:
                path = ""
            pixmap = QPixmap(path)
            if pixmap.isNull():
                label.clear()
                label.setText(self.tr("None"))
            else:
                label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _clear_images(self):
        self._clear_role(1)
        self._clear_role(2)

    def _clear_role(self, role):
        self._changed_roles.add(role)
        for key, current_role in list(self._roles.items()):
            if current_role == role:
                self._roles[key] = 0
                combo = self._combos.get(key)
                if combo:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(0)
                    combo.blockSignals(False)
        self._update_previews()

    def _save_candidate(self, image, role):
        role_name = "vertical" if role == 1 else "horizontal"
        if image["source"] == "vndb":
            return SystemUtils.save_image_to_covers(image["local_path"], image["game_id"], role_name)
        item = image["item"]
        game_id = f'sgdb{image["game_id"]}'
        full_url = item.get("full_url", "")
        saved = SteamGridDbManager.download_full_image(full_url, game_id, role_name) if full_url else ""
        return saved or SystemUtils.save_image_to_covers(image["local_path"], game_id, role_name)

    def accept(self):
        updates = {}
        for role, path_field, url_field in ((1, "cover_path", "cover_source_url"), (2, "layout_path", "layout_source_url")):
            if role not in self._changed_roles:
                continue
            image = self._selected_image(role)
            if image:
                saved = self._save_candidate(image, role)
                if not saved:
                    QMessageBox.warning(self, self.tr("Image not saved"), self.tr("Could not save the selected image. Please try again."))
                    return
                updates[path_field] = saved
                updates[url_field] = image["source_url"]
            else:
                updates[path_field] = ""
                updates[url_field] = ""
        for field, value in updates.items():
            setattr(self.current_game, field, value)
        self.image_updates = updates
        super().accept()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize and watched in (self.vndb_scroll.viewport(), self.sgdb_scroll.viewport()):
            self._resize_timer.start()
        elif event.type() == QEvent.Wheel:
            for key, combo in self._combos.items():
                if watched is combo:
                    scroll = self.vndb_scroll if key[0] == "vndb" else self.sgdb_scroll
                    event.ignore()
                    QApplication.sendEvent(scroll.viewport(), event)
                    return True
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        for worker in self._workers:
            worker.cancel()
        for worker in self.vndb_search.active_vndb_workers:
            worker.cancel()
        for worker in self.sgdb_search.active_sgdb_workers:
            worker.cancel()
        if self.sgdb_search.active_asset_worker:
            self.sgdb_search.active_asset_worker.cancel()
        self.settings.setValue("ImageManagementDialog/geometry", self.saveGeometry())
        super().hideEvent(event)

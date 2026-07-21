import config
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLineEdit, QLabel, QPushButton, QFileDialog,
    QCheckBox, QGroupBox, QScrollArea, QWidget,
    QGridLayout, QComboBox, QStackedWidget,
    QFrame, QSplitter, QStyle, QSizePolicy
)
from PySide6.QtCore import Qt, QSettings, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon, QPainter, QPalette
from ui.vndb_autocomplete import VndbAutocompleteLineEdit
from ui.sgdb_autocomplete import SgdbAutocompleteLineEdit
from vndb_manager import VndbReleaseImagesWorker
from system_utils import SystemUtils
from steamgrid_manager import SteamGridDbSearchWorker, SteamGridDbImagesWorker, SteamGridDbManager
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class AdvancedSettingsDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, prefix_type, current_game, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Advanced Settings {}").format(current_game.name))
        self.setMinimumWidth(450)
        self.resize(550, 600)

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        self.images_searched = False
        self.current_game = current_game
        self.selected_vndb_id = self.current_game.vndb

        self.sgdb_api_key = SettingsManager().get(config.USER_CONF_SGDB_API_KEY, "")
        self.sgdb_game_id = None
        self._sgdb_valid_items = []
        self._vndb_image_paths = []

        # Debounce timer for SGDB grid resize
        self._sgdb_resize_timer = QTimer(self)
        self._sgdb_resize_timer.setSingleShot(True)
        self._sgdb_resize_timer.setInterval(150)
        self._sgdb_resize_timer.timeout.connect(self._sgdb_rebuild_grid)

        # Debounce timer for the VNDB grid resize
        self._vndb_resize_timer = QTimer(self)
        self._vndb_resize_timer.setSingleShot(True)
        self._vndb_resize_timer.setInterval(150)
        self._vndb_resize_timer.timeout.connect(self._vndb_rebuild_grid)

        # Tracks combos the user explicitly changed
        self._user_modified_combos = set()  

        # Main layout
        self.main_outer_layout = QVBoxLayout(self)
        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)

        # UMU Fields
        self.edit_umu_store = QLineEdit(getattr(self.current_game, "umu_store", ""))
        self.edit_umu_id = QLineEdit(getattr(self.current_game, "umu_gameid", ""))
        
        self.label_umu_store = QLabel(self.tr("UMU Store:"))
        self.label_umu_id = QLabel(self.tr("UMU ID:"))

        # Proton Visibility Logic
        is_proton = (prefix_type == "proton")
        self.edit_umu_store.setVisible(is_proton)
        self.edit_umu_id.setVisible(is_proton)
        self.label_umu_store.setVisible(is_proton)
        self.label_umu_id.setVisible(is_proton)

        form.addRow(self.label_umu_store, self.edit_umu_store)
        form.addRow(self.label_umu_id, self.edit_umu_id)

        # Pre-launch Arguments
        self.edit_pre_args = QLineEdit(getattr(self.current_game, "pre_launch_args", ""))
        form.addRow(self.tr("Pre-Launch Command:"), self.edit_pre_args)

        # Arguments
        self.edit_arguments = QLineEdit(getattr(self.current_game, "arguments", ""))
        form.addRow(self.tr("Game Arguments:"), self.edit_arguments)

        # Pre-launch Script
        self.edit_pre_script = QLineEdit(getattr(self.current_game, "pre_launch_script", ""))
        self.btn_pre_script = QPushButton("...")
        self.btn_pre_script.clicked.connect(lambda: self.browse_file(self.edit_pre_script))

        pre_script_layout = QHBoxLayout()
        pre_script_layout.addWidget(self.edit_pre_script)
        pre_script_layout.addWidget(self.btn_pre_script)
        form.addRow(self.tr("Pre-Launch Script:"), pre_script_layout)
 
        # Pre-launch Script Wait
        self.chk_pre_script_wait = QCheckBox(self.tr("Wait for game to open before executing script"))
        self.chk_pre_script_wait.setChecked(getattr(self.current_game, "pre_launch_script_wait", False))
        form.addRow("", self.chk_pre_script_wait)

        # Exit Script
        self.edit_exit_script = QLineEdit(getattr(self.current_game, "exit_script", ""))
        self.btn_exit_script = QPushButton("...")
        self.btn_exit_script.clicked.connect(lambda: self.browse_file(self.edit_exit_script))
        
        exit_script_layout = QHBoxLayout()
        exit_script_layout.addWidget(self.edit_exit_script)
        exit_script_layout.addWidget(self.btn_exit_script)
        form.addRow(self.tr("Exit Script:"), exit_script_layout)

        self.scroll_layout.addLayout(form)

        # Space form from image section
        self.scroll_layout.addSpacing(10)

        self.lbl_vndb_instructions = QLabel(self.tr("Note: You can only select 1 vertical cover and 1 horizontal layout image to be used with the Steam shortcut."))
        self.lbl_vndb_instructions.setStyleSheet("font-style: italic;")
        self.lbl_vndb_instructions.setWordWrap(True)
        self.scroll_layout.addWidget(self.lbl_vndb_instructions)

        # Current images Display
        self.current_assets_box = QGroupBox(self.tr("Current Images"))
        assets_outer_layout = QVBoxLayout()
        assets_outer_layout.setContentsMargins(0, 0, 0, 0)
        assets_outer_layout.setSpacing(6)

        self.current_assets_layout = QHBoxLayout()
        self.current_assets_layout.setAlignment(Qt.AlignLeft)

        self.curr_v_label = QLabel()
        self.curr_v_label.setFixedHeight(160)
        self.curr_v_label.setMinimumWidth(40)
        self.curr_v_label.setStyleSheet("border: 1px solid #444; background: #222;")
        self.curr_v_label.setAlignment(Qt.AlignCenter)

        self.curr_h_label = QLabel()
        self.curr_h_label.setFixedHeight(160)
        self.curr_h_label.setMinimumWidth(40)
        self.curr_h_label.setStyleSheet("border: 1px solid #444; background: #222;")

        self.current_assets_layout.addWidget(self.curr_v_label)
        self.current_assets_layout.addSpacing(20)
        self.current_assets_layout.addWidget(self.curr_h_label)
        self.current_assets_layout.addStretch()

        self.btn_clear_assets = QPushButton("🗑")
        self.btn_clear_assets.setToolTip(self.tr("Remove current cover images"))
        self.btn_clear_assets.setFixedSize(64, 64)
        self.btn_clear_assets.setStyleSheet("""
            QPushButton {
                background: transparent;
                border-radius: 4px;
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background: palette(button);
            }
            QPushButton:pressed {
                background: palette(dark);
            }
        """)
        self.btn_clear_assets.clicked.connect(self._clear_current_assets)

        assets_outer_layout.addLayout(self.current_assets_layout)
        assets_outer_layout.addWidget(self.btn_clear_assets, 0, Qt.AlignLeft)

        self.current_assets_box.setLayout(assets_outer_layout)
        self.scroll_layout.addWidget(self.current_assets_box)
        self.current_assets_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        
        # Initially update the thumbnails
        self._update_current_asset_thumbnails()

        # VNDB Release Images Section
        self.vndb_group = QGroupBox(self.tr("VNDB Release Images"))
        vndb_inner_layout = QVBoxLayout(self.vndb_group)

        self.search_bar = VndbAutocompleteLineEdit(self)
        self.search_bar.setPlaceholderText(self.tr("Game name or vndb id..."))
        self.search_bar.vn_selected.connect(self.on_vn_selected)
        vndb_inner_layout.addWidget(self.search_bar)

        self.vndb_stack = QStackedWidget()

        self.lbl_loading = QLabel(self.tr("Search for a visual novel to load images."))
        self.lbl_loading.setAlignment(Qt.AlignCenter)
        self.vndb_stack.addWidget(self.lbl_loading)

        self.gallery_container = QWidget()
        self.gallery_layout = QGridLayout(self.gallery_container)
        self.vndb_stack.addWidget(self.gallery_container)

        vndb_inner_layout.addWidget(self.vndb_stack)

        self.main_scroll.setWidget(self.scroll_content)
        self.main_outer_layout.addWidget(self.main_scroll)

        self.scroll_layout.addSpacing(10)

       # SteamGridDB
        self.sgdb_group = QGroupBox(self.tr("SteamGridDB Images"))
        sgdb_main_layout = QVBoxLayout(self.sgdb_group)

        self.lbl_sgdb_status = QLabel("")
        self.lbl_sgdb_status.setStyleSheet("color: #888;")

        self.lbl_sgdb_loading = QLabel(self.tr("Search for a game to load images."))
        self.lbl_sgdb_loading.setAlignment(Qt.AlignCenter)

        # Initialize the new Autocomplete Search Bar
        self.sgdb_search_edit = SgdbAutocompleteLineEdit(self)
        self.sgdb_search_edit.setPlaceholderText(self.tr("Game name..."))
        self.sgdb_search_edit.assets_ready.connect(self._on_sgdb_images_ready)
        self.sgdb_search_edit.status_changed.connect(self.lbl_sgdb_status.setText)
        self.sgdb_search_edit.game_selected.connect(self._on_sgdb_game_selected)
        
        sgdb_main_layout.addWidget(self.sgdb_search_edit)
        sgdb_main_layout.addWidget(self.lbl_sgdb_status)
        sgdb_main_layout.addWidget(self.lbl_sgdb_loading)

        self.sgdb_images_widget = QWidget()
        self.sgdb_images_layout = QGridLayout(self.sgdb_images_widget)
        self.sgdb_images_layout.setSpacing(10)
        self.sgdb_images_layout.setContentsMargins(0, 0, 0, 0)
        self.sgdb_images_layout.setAlignment(Qt.AlignTop)

        sgdb_main_layout.addWidget(self.sgdb_images_widget)

        # Qsplitter spacing
        self.groups_splitter = QSplitter(Qt.Vertical)        
        self.groups_splitter.addWidget(self.vndb_group)
        self.groups_splitter.addWidget(self.sgdb_group)        
        self.groups_splitter.setChildrenCollapsible(True)         
        self.vndb_group.setMinimumHeight(0)
        self.sgdb_group.setMinimumHeight(0)
        self.groups_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #333;
                height: 6px;
                margin: 2px 0px;
            }
            QSplitter::handle:hover { background-color: #555; }
        """)
                
        self.scroll_layout.addWidget(self.groups_splitter)

        # State Tracking
        self.main_scroll.setWidget(self.scroll_content)
        self.main_outer_layout.addWidget(self.main_scroll)
        self.vndb_image_combos = []
        self.sgdb_image_combos = []
        self.active_image_worker = None

        # Save / Cancel Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(self.tr("Save"))
        save_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        save_btn.setAutoDefault(False)
        save_btn.setDefault(False)

        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.setAutoDefault(False)
        
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        self.main_outer_layout.addLayout(btn_layout)

        # Restore previous window size
        self._restore_state()

    def browse_file(self, target_line_edit):
        """Opens file system to select a script."""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            self.tr("Select Script File"),
            "",
            self.tr("All Files (*);;Shell Scripts (*.sh)")
        )
        if path:
            target_line_edit.setText(path)

    def accept(self):
        """Saves values directly back to the unsaved in-memory game card."""

        # Process VNDB image selections
        if self.images_searched and self.selected_vndb_id:
            for combo in self.vndb_image_combos:
                if id(combo) not in self._user_modified_combos:
                    # Not modified, dont change
                    continue

                role_index = combo.currentIndex()
                temp_path = combo.property("image_path")
                source_url = combo.property("source_url")
                if role_index == 0:
                    # Explicitly set to None, delete target image
                    if temp_path and SystemUtils.are_files_identical(temp_path, self.current_game.cover_path):
                        self.current_game.cover_path = ""
                        self.current_game.cover_source_url = ""
                    elif temp_path and SystemUtils.are_files_identical(temp_path, self.current_game.layout_path):
                        self.current_game.layout_path = ""
                        self.current_game.layout_source_url = ""
                elif role_index == 1 and temp_path:
                    saved = SystemUtils.save_image_to_covers(temp_path, self.selected_vndb_id, "vertical")
                    if saved:
                        self.current_game.cover_path = saved
                        self.current_game.cover_source_url = source_url
                elif role_index == 2 and temp_path:
                    saved = SystemUtils.save_image_to_covers(temp_path, self.selected_vndb_id, "horizontal")
                    if saved:
                        self.current_game.layout_path = saved
                        self.current_game.cover_source_url = source_url

        # SteamGridDB image selections
        if self.sgdb_game_id and self.sgdb_api_key:
            sgdb_id_str = f"sgdb{self.sgdb_game_id}"
            for combo in self.sgdb_image_combos:
                if id(combo) not in self._user_modified_combos:
                    # Not modified, dont change
                    continue

                role_index = combo.currentIndex()
                parent_widget = combo.parentWidget()
                if not hasattr(parent_widget, "item"):
                    continue
                item = parent_widget.item
                item_url = item.get("full_url", "")
                if role_index == 0:
                    # Explicitly set to None, delete target image
                    if item_url and item_url == self.current_game.cover_source_url:
                        self.current_game.cover_path = ""
                        self.current_game.cover_source_url = ""
                    elif item_url and item_url == self.current_game.layout_source_url:
                        self.current_game.layout_path = ""
                        self.current_game.layout_source_url = ""
                elif role_index == 1:
                    saved = self._sgdb_save_full_image(item, sgdb_id_str, "vertical")
                    if saved:
                        self.current_game.cover_path = saved
                        self.current_game.cover_source_url = item_url
                elif role_index == 2:
                    saved = self._sgdb_save_full_image(item, sgdb_id_str, "horizontal")
                    if saved:
                        self.current_game.layout_path = saved
                        self.current_game.layout_source_url = item_url

        logger.debug(
            f"[AdvancedSettings.accept] cover_path='{self.current_game.cover_path}' "
            f"layout_path='{self.current_game.layout_path}'"
        )

        self.current_game.umu_store = self.edit_umu_store.text()
        self.current_game.umu_gameid = self.edit_umu_id.text()
        self.current_game.pre_launch_args = self.edit_pre_args.text()
        self.current_game.arguments = self.edit_arguments.text()
        self.current_game.pre_launch_script = self.edit_pre_script.text()
        self.current_game.pre_launch_script_wait = self.chk_pre_script_wait.isChecked()
        self.current_game.exit_script = self.edit_exit_script.text()
        super().accept()

    def on_vn_selected(self, vn_data):
        """Fetches release images for a selected VNDB entry."""
        self.selected_vndb_id = vn_data.get("id")
        self.images_searched = True

        # Get the main cover url from the vn_data to ensure it's included
        main_cover_url = vn_data.get("image", {}).get("url") if vn_data.get("image") else None

        if not self.selected_vndb_id:
            return

        # Clear existing images
        self.clear_image_gallery()
        
        # Show loading state
        self.lbl_loading.setText(self.tr("Fetching images..."))
        self.vndb_stack.setCurrentIndex(0)

        # Cancel previous worker if still running
        if self.active_image_worker:
            self.active_image_worker.cancel()

        # Start fetching
        self.active_image_worker = VndbReleaseImagesWorker(self.selected_vndb_id, main_cover_url)
        self.active_image_worker.images_ready.connect(self.populate_image_gallery)
        self.active_image_worker.start()

    def clear_image_gallery(self):
        """Removes all widgets from the VNDB scroll grid layout."""
        self._vndb_image_paths = []
        self._vndb_resize_timer.stop()
        self.vndb_image_combos.clear()
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def populate_image_gallery(self, image_paths):
        """Initializes the gallery view with fetched images."""
        self.clear_image_gallery()

        if not image_paths:
            self.lbl_loading.setText(self.tr("No images found for this release."))
            self.vndb_stack.setCurrentIndex(0)
            return

        self.vndb_stack.setCurrentIndex(1)
        self._vndb_image_paths = list(image_paths)
        self._vndb_rebuild_grid()

    def _vndb_rebuild_grid(self):
        """Recalculates VNDB grid layout based on current dialog width."""
        if not self._vndb_image_paths:
            return

        MAX_HEIGHT = 200

        # Snapshot current combo selections before clearing
        previous_selections: dict[str, int] = {}
        for combo in self.vndb_image_combos:
            path = combo.property("image_path")
            if path:
                previous_selections[path] = combo.currentIndex()

        # Clear the grid and combo tracking list
        self.vndb_image_combos.clear()
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Measure scaled widths for all valid paths
        valid_paths = []  # list of list of (path, url, scaled_width)
        for img_dict in self._vndb_image_paths:
            path = img_dict.get("local_path", "")
            url = img_dict.get("url", "")

            pixmap = QPixmap(path)
            if pixmap.isNull():
                continue
            ph = pixmap.height()
            scaled_w = int(pixmap.width() * MAX_HEIGHT / ph) if ph > 0 else MAX_HEIGHT
            valid_paths.append((path, url, scaled_w))

        if not valid_paths:
            return

        # Determine available width
        spacing = self.gallery_layout.spacing()
        available_w = self.main_scroll.viewport().width() - 36
        if available_w <= 0:
            available_w = self.width() - 36

        # Compute column count
        max_img_w = max(scaled_w for _, _, scaled_w in valid_paths)
        columns = max(1, (available_w + spacing) // (max_img_w + spacing))

        # Build grid
        row, col = 0, 0
        for path, url, _ in valid_paths:
            container = QWidget()
            cont_layout = QVBoxLayout(container)
            cont_layout.setContentsMargins(5, 5, 5, 5)

            lbl_img = QLabel()
            lbl_img.setAlignment(Qt.AlignCenter)
            lbl_img.setFixedHeight(MAX_HEIGHT)

            pixmap = QPixmap(path)
            if not pixmap.isNull():
                lbl_img.setPixmap(pixmap.scaledToHeight(MAX_HEIGHT, Qt.SmoothTransformation))
            else:
                lbl_img.setText(self.tr("Invalid Image"))

            combo = QComboBox()
            combo.addItems([self.tr("None"), self.tr("Vertical Cover"), self.tr("Horizontal Layout")])
            combo.setProperty("image_path", path)
            combo.setProperty("source_url", url)
            combo.blockSignals(True)

            if path in previous_selections:
                # Restore user's in-session selection
                combo.setCurrentIndex(previous_selections[path])
            elif self.current_game.cover_path and SystemUtils.are_files_identical(path, self.current_game.cover_path):
                combo.setCurrentIndex(1)
            elif self.current_game.layout_path and SystemUtils.are_files_identical(path, self.current_game.layout_path):
                combo.setCurrentIndex(2)

            combo.blockSignals(False)
            combo.currentIndexChanged.connect(lambda idx, c=combo: self.on_image_role_changed(idx, c))
            self.vndb_image_combos.append(combo)

            cont_layout.addWidget(lbl_img)
            cont_layout.addWidget(combo)

            self.gallery_layout.addWidget(container, row, col)

            col += 1
            if col >= columns:
                col = 0
                row += 1

    def on_image_role_changed(self, index, changed_combo):
        """
        Ensures mutual exclusivity for 'Vertical Cover' (index 1) and 'Horizontal Layout'
        (index 2) across both the VNDB and SGDB sections: only one of each role can be
        selected at any time in the entire dialog.
        """
        self._user_modified_combos.add(id(changed_combo))

        if index == 0:
            return

        all_combos = self.vndb_image_combos + self.sgdb_image_combos

        # Block signals on all combos to avoid recursive triggers
        for combo in all_combos:
            combo.blockSignals(True)

        for combo in all_combos:
            if combo != changed_combo and combo.currentIndex() == index:
                combo.setCurrentIndex(0)

        for combo in all_combos:
            combo.blockSignals(False)

    def _update_current_asset_thumbnails(self):
        """Refreshes the thumbnail previews of saved assets."""
        v_exists = self._set_thumbnail_preview(self.curr_v_label, self.current_game.cover_path, self.tr("No Cover"), 112)
        h_exists = self._set_thumbnail_preview(self.curr_h_label, self.current_game.layout_path, self.tr("No Layout"), 200)
        self.current_assets_box.setVisible(v_exists or h_exists)

    def _set_thumbnail_preview(self, label, path, placeholder_text, default_width):
        """Sets a scaled pixmap to a label or displays placeholder text."""
        MAX_HEIGHT = 160
        pix = QPixmap(path)
        if not pix.isNull():
            scaled_pix = pix.scaledToHeight(MAX_HEIGHT, Qt.SmoothTransformation)
            label.setPixmap(scaled_pix)
            label.setFixedWidth(scaled_pix.width())
            label.show()
            return True
        
        label.hide()
        return False

    def _sgdb_save_full_image(self, item: dict, game_id_str: str, role: str) -> str:
        """Downloads full SGDB image or falls back to local thumbnail."""
        full_url = item.get("full_url", "")
        
        if full_url:
            saved_path = SteamGridDbManager.download_full_image(full_url, game_id_str, role)
            if saved_path:
                return saved_path

        # Fall back to already downloaded thumb, should never happen tho
        return SystemUtils.save_image_to_covers(item["local_path"], game_id_str, role)

    def _on_sgdb_game_selected(self, game_data):
        """Update game ID when an item is chosen from autocomplete."""
        self.sgdb_game_id = game_data.get("id")

    def _on_sgdb_images_ready(self, grids, heroes):
        """Caches valid SGDB items and builds the grid."""
        self.lbl_sgdb_status.hide()
        self.lbl_sgdb_loading.hide()

        # Clear existing SGDB images
        while self.sgdb_images_layout.count():
            item = self.sgdb_images_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not grids and not heroes:
            self.lbl_sgdb_status.setText(self.tr("No images found."))
            self.lbl_sgdb_status.show()
            return

        all_images = grids + heroes
        MAX_HEIGHT = 200

        valid_items = []
        for item in all_images:
            local_path = item.get("local_path", "")
            if not local_path:
                continue
            pixmap = QPixmap(local_path)
            if pixmap.isNull():
                continue
            ph = pixmap.height()
            scaled_w = int(pixmap.width() * MAX_HEIGHT / ph) if ph > 0 else MAX_HEIGHT
            valid_items.append((item, local_path, scaled_w))

        self._sgdb_valid_items = valid_items
        self._sgdb_rebuild_grid()

    def _sgdb_rebuild_grid(self):
        """Reconstructs the SGDB image grid based on current dialog width."""
        if not self._sgdb_valid_items:
            return

        MAX_HEIGHT = 200

        # Snapshot current combo selections before clearing
        previous_selections: dict[str, int] = {}
        for combo in self.sgdb_image_combos:
            path = combo.property("image_path")
            if path:
                previous_selections[path] = combo.currentIndex()

        # Clear the grid and combo tracking list
        self.sgdb_image_combos.clear()
        while self.sgdb_images_layout.count():
            item = self.sgdb_images_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Determine available width
        spacing = self.sgdb_images_layout.spacing()
        available_w = self.main_scroll.viewport().width() - 36
        if available_w <= 0:
            available_w = self.width() - 36

        max_img_w = max(scaled_w for _, _, scaled_w in self._sgdb_valid_items)
        max_cols = max(1, (available_w + spacing) // (max_img_w + spacing))

        # Build grid
        row, col = 0, 0
        for item, local_path, _ in self._sgdb_valid_items:
            widget = SelectableImageWidget(local_path, item, max_height=MAX_HEIGHT)

            if local_path in previous_selections:
                widget.combo.blockSignals(True)
                widget.combo.setCurrentIndex(previous_selections[local_path])
                widget.combo.blockSignals(False)
            else:
                item_url = item.get("full_url", "")
                cover_url = getattr(self.current_game, "cover_source_url", "")
                layout_url = getattr(self.current_game, "layout_source_url", "")
                # logger.debug(f"[SGDB Preselect] item_url='{item_url}'")
                # logger.debug(f"[SGDB Preselect] cover_source_url='{cover_url}'")
                # logger.debug(f"[SGDB Preselect] layout_source_url='{layout_url}'")
                # logger.debug(f"[SGDB Preselect] match_cover={item_url == cover_url}, match_layout={item_url == layout_url}")
                widget.combo.blockSignals(True)
                if item_url and item_url == cover_url:
                    widget.combo.setCurrentIndex(1)
                elif item_url and item_url == layout_url:
                    widget.combo.setCurrentIndex(2)
                widget.combo.blockSignals(False)

            self.sgdb_image_combos.append(widget.combo)
            widget.combo.currentIndexChanged.connect(
                lambda idx, cb=widget.combo: self.on_image_role_changed(idx, cb)
            )

            self.sgdb_images_layout.addWidget(widget, row, col, Qt.AlignCenter)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def _clear_current_assets(self):
        """Clears both cover and layout paths from the game and refreshes the UI."""
        self.current_game.cover_path = ""
        self.current_game.layout_path = ""
        self.current_game.cover_source_url = ""
        self.current_game.layout_source_url = ""
        self._update_current_asset_thumbnails()

    def _update_current_asset_thumbnails(self):
        """Refreshes the thumbnail previews of saved assets."""
        v_exists = self._set_thumbnail_preview(self.curr_v_label, self.current_game.cover_path, self.tr("No Cover"), 112)
        h_exists = self._set_thumbnail_preview(self.curr_h_label, self.current_game.layout_path, self.tr("No Layout"), 200)
        any_exists = v_exists or h_exists
        self.current_assets_box.setVisible(any_exists)
        self.btn_clear_assets.setVisible(any_exists)

    def keyPressEvent(self, event):
        """Prevents the dialog from closing when 'Enter' or 'Return' is pressed."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            # If the focus is on a LineEdit that isn't the autocomplete, just ignore it.
            # Autocomplete line edits handle their own key events.
            event.ignore()
            return
        super().keyPressEvent(event)

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("AdvancedSettingsDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def resizeEvent(self, event):
        """Kick off debounced grid reflows for both sections whenever the dialog is resized."""
        super().resizeEvent(event)
        if self._sgdb_valid_items:
            self._sgdb_resize_timer.start()  # restarts the timer on each call
        if self._vndb_image_paths:
            self._vndb_resize_timer.start()

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        if self.active_image_worker:
            self.active_image_worker.cancel()
        self.settings.setValue("AdvancedSettingsDialog/geometry", self.saveGeometry())
        super().closeEvent(event)
    
    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("AdvancedSettingsDialog/geometry", self.saveGeometry())
        super().hideEvent(event)

class SelectableImageWidget(QFrame):
    def __init__(self, local_path: str, item: dict, max_height: int, parent=None):
        super().__init__(parent)
        self.item = item
        self.local_path = local_path
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # The Image
        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setFixedHeight(max_height) # Forced height consistency
        
        pixmap = QPixmap(local_path)
        if not pixmap.isNull():
            # Scale to height; width adjusts automatically based on aspect ratio
            self.lbl_img.setPixmap(pixmap.scaledToHeight(max_height, Qt.SmoothTransformation))
        else:
            self.lbl_img.setText(self.tr("Invalid Image"))

        # Metadata (Style/Author)
        author = item.get("author", self.tr("Unknown"))
        style  = item.get("style", self.tr("Default"))
        lbl_meta = QLabel(f"{style} • {author}")
        lbl_meta.setStyleSheet("font-size: 10px; color: #888;")
        lbl_meta.setAlignment(Qt.AlignCenter)
        lbl_meta.setWordWrap(True)

        # The Combo Box
        self.combo = QComboBox()
        self.combo.addItems([self.tr("None"), self.tr("Vertical Cover"), self.tr("Horizontal Layout")])
        self.combo.setProperty("image_path", local_path)
        self.combo.setFixedWidth(160)

        layout.addWidget(self.lbl_img, 0, Qt.AlignCenter)
        layout.addWidget(lbl_meta)
        layout.addWidget(self.combo, 0, Qt.AlignCenter)
import config
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, 
    QLineEdit, QLabel, QPushButton, QFileDialog,
    QCheckBox, QGroupBox, QScrollArea, QWidget, 
    QGridLayout, QComboBox, QStackedWidget
)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPixmap
from ui.vndb_autocomplete import VndbAutocompleteLineEdit
from vndb_manager import VndbReleaseImagesWorker
from system_utils import SystemUtils

logger = logging.getLogger(__name__)

class AdvancedSettingsDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, prefix_type, current_game, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr(f"Advanced Settings {current_game.name}"))
        self.setMinimumWidth(450)
        self.resize(550, 600)

        self.images_searched = False
        self.current_game = current_game
        self.selected_vndb_id = self.current_game.vndb

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

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

        self.lbl_vndb_instructions = QLabel(self.tr("Note: You can only select 1 vertical cover and 1 horizontal layout image for Steam."))
        self.lbl_vndb_instructions.setStyleSheet("font-style: italic;")
        self.lbl_vndb_instructions.setWordWrap(True)
        self.scroll_layout.addWidget(self.lbl_vndb_instructions)

        # Current images Display
        self.current_assets_box = QGroupBox(self.tr("Current Images"))
        self.current_assets_layout = QHBoxLayout()
        self.current_assets_layout.setAlignment(Qt.AlignLeft)
        
        self.curr_v_label = QLabel()
        self.curr_v_label.setFixedHeight(160)
        self.curr_v_label.setMinimumWidth(40) # Minimum to show some background
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
        
        self.current_assets_box.setLayout(self.current_assets_layout)
        self.scroll_layout.addWidget(self.current_assets_box)
        
        # Initially update the thumbnails
        self._update_current_asset_thumbnails()

        # VNDB Release Images Section
        self.vndb_group = QGroupBox(self.tr("VNDB Release Images"))
        vndb_inner_layout = QVBoxLayout(self.vndb_group)

        # Autocomplete Search Bar
        self.search_bar = VndbAutocompleteLineEdit(self)
        self.search_bar.setPlaceholderText(self.tr("Search VNDB to fetch release images..."))
        self.search_bar.vn_selected.connect(self.on_vn_selected)
        vndb_inner_layout.addWidget(self.search_bar)

        self.vndb_stack = QStackedWidget()

        self.lbl_loading = QLabel(self.tr("Search for a visual novel to load images."))
        self.lbl_loading.setAlignment(Qt.AlignCenter)
        self.vndb_stack.addWidget(self.lbl_loading)

        # Page 1: Scroll Area for Images
        self.gallery_container = QWidget()
        self.gallery_layout = QGridLayout(self.gallery_container)
        self.vndb_stack.addWidget(self.gallery_container)

        vndb_inner_layout.addWidget(self.vndb_stack)
        self.scroll_layout.addWidget(self.vndb_group)

        self.main_scroll.setWidget(self.scroll_content)
        self.main_outer_layout.addWidget(self.main_scroll)


        # State tracking for image combo boxes
        self.image_combos = []
        self.active_image_worker = None

        # Save / Cancel Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(self.tr("Save"))
        save_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        cancel_btn = QPushButton(self.tr("Cancel"))
        
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
            "All Files (*);;Shell Scripts (*.sh)"
        )
        if path:
            target_line_edit.setText(path)

    def accept(self):
        """Saves values directly back to the unsaved in-memory game card."""       
        
        # Only touch images if a search was actively performed
        if self.images_searched:            
            # We reset paths here because if they are in "Search Mode", 
            # any combo left as "None" means they want to remove that image.
            self.current_game.cover_path = ""
            self.current_game.layout_path = ""

            if self.selected_vndb_id and hasattr(self, 'image_combos'):
                for combo in self.image_combos:
                    role_index = combo.currentIndex()
                    if role_index == 0: 
                        continue
                    
                    # Fetch the path directly from the combo box property
                    temp_path = combo.property("image_path")
                    if not temp_path:
                        continue
                    
                    if role_index == 1:
                        self.current_game.cover_path = SystemUtils.save_image_to_covers(
                            temp_path, self.selected_vndb_id, "vertical"
                        )
                    elif role_index == 2:
                        self.current_game.layout_path = SystemUtils.save_image_to_covers(
                            temp_path, self.selected_vndb_id, "horizontal"
                        )

        logger.debug(f"[AdvancedSettings.accept] cover_path='{self.current_game.cover_path}' layout_path='{self.current_game.layout_path}'")
        self.current_game.umu_store = self.edit_umu_store.text()
        self.current_game.umu_gameid = self.edit_umu_id.text()
        self.current_game.pre_launch_args = self.edit_pre_args.text()
        self.current_game.arguments = self.edit_arguments.text()
        self.current_game.pre_launch_script = self.edit_pre_script.text()
        self.current_game.pre_launch_script_wait = self.chk_pre_script_wait.isChecked()
        self.current_game.exit_script = self.edit_exit_script.text()
        super().accept()

    def on_vn_selected(self, vn_data):
        """Triggered when user clicks a game in the autocomplete popup."""
        self.selected_vndb_id = vn_data.get("id")

        self.images_searched = True

        # Try to get the main cover url from the vn_data to ensure it's included
        main_cover_url = vn_data.get("image", {}).get("url") if vn_data.get("image") else None

        if not self.selected_vndb_id:
            return

        # Clear existing images
        self.clear_image_gallery()
        
        # Show loading state seamlessly
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
        """Removes all widgets from the scroll grid layout."""
        self.image_combos.clear()
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def populate_image_gallery(self, image_paths):
        """Renders the downloaded images into the grid with combo boxes."""
        self.clear_image_gallery()

        if not image_paths:
            self.lbl_loading.setText(self.tr("No images found for this release."))
            self.vndb_stack.setCurrentIndex(0)
            return

        # Switch view to the scroll area
        self.vndb_stack.setCurrentIndex(1)

        # 3 columns
        columns = 3
        row, col = 0, 0

        # Max image size
        MAX_HEIGHT = 200 

        for path in image_paths:
            container = QWidget()
            cont_layout = QVBoxLayout(container)
            cont_layout.setContentsMargins(5, 5, 5, 5)

            # Image Label
            lbl_img = QLabel()
            lbl_img.setAlignment(Qt.AlignCenter)
            lbl_img.setFixedHeight(MAX_HEIGHT) # Keep row heights uniform
            
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                # Scaling to height to maintain aspect ratio as requested previously
                scaled_pixmap = pixmap.scaledToHeight(MAX_HEIGHT, Qt.SmoothTransformation)
                lbl_img.setPixmap(scaled_pixmap)
            else:
                lbl_img.setText(self.tr("Invalid Image"))
            
            # Combo Box
            combo = QComboBox()
            combo.addItems([self.tr("None"), self.tr("Vertical Cover"), self.tr("Horizontal Layout")])
            combo.setProperty("image_path", path)

            # Block signals to prevent "mutually exclusive" logic from firing during setup
            combo.blockSignals(True)

            # Check both cover_path and layout_path for pre-selection
            if self.current_game.cover_path and SystemUtils.are_files_identical(path, self.current_game.cover_path):
                combo.setCurrentIndex(1)
            elif self.current_game.layout_path and SystemUtils.are_files_identical(path, self.current_game.layout_path):
                combo.setCurrentIndex(2)
            combo.blockSignals(False)

            combo.currentIndexChanged.connect(lambda idx, c=combo: self.on_image_role_changed(idx, c))
            self.image_combos.append(combo)

            cont_layout.addWidget(lbl_img)
            cont_layout.addWidget(combo)

            self.gallery_layout.addWidget(container, row, col)

            col += 1
            if col >= columns:
                col = 0
                row += 1

    def on_image_role_changed(self, index, changed_combo):
        """Ensures mutual exclusivity for 'Vertical Cover' (index 1) and 'Horizontal Layout' (index 2)."""
        if index == 0:  # "None" selected
            return

        # Temporarily block signals to avoid recursive triggers
        for combo in self.image_combos:
            combo.blockSignals(True)

        for combo in self.image_combos:
            if combo != changed_combo:
                # If another combo has the same role selected, reset it to "None"
                if combo.currentIndex() == index:
                    combo.setCurrentIndex(0)

        for combo in self.image_combos:
            combo.blockSignals(False)

    def _update_current_asset_thumbnails(self):
        """Updates the small previews of currently saved images."""
        has_assets = False
        MAX_HEIGHT = 160

        import os

        def set_preview(label, path, placeholder_text, default_width):
            if path and os.path.exists(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    # Scale based on height while keeping the original aspect ratio
                    scaled_pix = pix.scaledToHeight(MAX_HEIGHT, Qt.SmoothTransformation)
                    label.setPixmap(scaled_pix)
                    # Adjust label width so it perfectly fits the image
                    label.setFixedWidth(scaled_pix.width())
                    return True
            
            # Fallback if image doesn't exist
            label.clear()
            label.setText(self.tr(placeholder_text))
            label.setFixedWidth(default_width)
            return False


        v_exists = set_preview(self.curr_v_label, self.current_game.cover_path, "No Cover", 112)
        h_exists = set_preview(self.curr_h_label, self.current_game.layout_path, "No Layout", 200)
            
        self.current_assets_box.setVisible(v_exists or h_exists)

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("AdvancedSettingsDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

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
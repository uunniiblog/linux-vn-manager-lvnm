import config
import json
import logging
import urllib.parse
import requests
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QFileDialog, QScrollArea, QWidget,
    QMessageBox, QSizePolicy
)
from PySide6.QtCore import Signal, QSettings, Qt
from ui.console_dialog import ConsoleDialog
from game_manager import GameManager
from prefix_manager import PrefixManager
from runner_manager import RunnerManagerInterface
from runner_manager_protonge import RunnerManagerProtonGE
from runner_manager_kron4ek import RunnerManagerKron4ek
from settings_manager import SettingsManager
from model.game_card import GameCard
from vndb_manager import VndbManager
from ui.vndb_autocomplete import VndbAutocompleteLineEdit

logger = logging.getLogger(__name__)

READONLY_STYLE = "color: #888888;"

class ImportGameDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    # Emitted when finished
    import_finished = Signal()  

    def __init__(self, import_path: str, parent=None):
        super().__init__(parent)
        self.import_path = import_path
        self.json_data = None
        self.game_data = {}
        self.prefix_data = {}
        self.setWindowTitle(self.tr("Import Game"))
        self.resize(650, 550)

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)
        self.user_settings = SettingsManager()
        self.savedata_settings = self.user_settings.get(config.USER_CONF_SAVEDATA, {})

        if not self._load_json():
            return

        self._build_ui()

    def _load_json(self) -> bool:
        try:
            with open(self.import_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
            self.game_data = self.json_data.get("game", {})
            self.prefix_data = self.json_data.get("prefix", {})
            return True
        except Exception as e:
            logger.error(f"Failed to read import file: {e}")
            return False

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # Scroll area so it doesn't overflow on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(12)

        # Editable Fields
        editable_group = QGroupBox(self.tr("Game Info"))
        editable_form = QFormLayout(editable_group)
        editable_form.setLabelAlignment(Qt.AlignLeft)

        # VNDB autocomplete
        self.edit_name = VndbAutocompleteLineEdit()
        self.edit_name.setText(self.game_data.get("name", ""))
        editable_form.addRow(self.tr("Name *"), self.edit_name)
        self.edit_name.vn_selected.connect(self._on_autocomplete_selected)

        path_layout = QHBoxLayout()
        self.edit_path = QLineEdit(self.game_data.get("path", ""))
        self.edit_path.setPlaceholderText(self.tr("Path to game .exe"))
        self.btn_browse = QPushButton(self.tr("Browse"))
        self.btn_browse.clicked.connect(self._browse_exe)
        path_layout.addWidget(self.edit_path)
        path_layout.addWidget(self.btn_browse)
        editable_form.addRow(self.tr("Executable *"), path_layout)

        self.edit_vndb = QLineEdit(self.game_data.get("vndb", ""))
        self.edit_vndb.setPlaceholderText(self.tr("e.g. v12345  (optional)"))
        editable_form.addRow(self.tr("VNDB ID"), self.edit_vndb)

        content_layout.addWidget(editable_group)

        # Read-only Game Fields 
        game_ro_group = QGroupBox(self.tr("Game Settings"))
        game_ro_form = QFormLayout(game_ro_group)
        game_ro_form.setLabelAlignment(Qt.AlignLeft)

        self._add_readonly_row(game_ro_form, self.tr("Last Updated Date"),      self.game_data.get("update_date", ""))

        # UMU — only show if non-default
        umu_id    = self.game_data.get("umu-gameid", "umu-default")
        umu_store = self.game_data.get("umu-store", "none")
        if umu_id != "umu-default":
            self._add_readonly_row(game_ro_form, self.tr("UMU Game ID"), umu_id)
        if umu_store != "none":
            self._add_readonly_row(game_ro_form, self.tr("UMU Store"), umu_store)

        # Env vars
        envvars = self.game_data.get("envvar", {})
        if envvars:
            env_text = "\n".join(f"{k}={v}" for k, v in envvars.items())
        else:
            env_text = self.tr("None")
        self._add_readonly_row(game_ro_form, self.tr("Env Vars"), env_text)

        # Gamescope
        gamescope = self.game_data.get("gamescope", {})
        if gamescope.get("enabled") == "true":
            self._add_readonly_row(game_ro_form, self.tr("Gamescope"), gamescope.get("parameters", ""))
        else:
            self._add_readonly_row(game_ro_form, self.tr("Gamescope"), self.tr("Disabled"))

        # DLL overrides — only show if not empty
        dlloverrides = self.game_data.get("dlloverride", {})
        if dlloverrides:
            dll_text = "  ".join(f"{k}={v}" for k, v in dlloverrides.items())
            self._add_readonly_row(game_ro_form, self.tr("DLL Overrides"), dll_text)

        content_layout.addWidget(game_ro_group)

        #  Read-only Prefix Fields
        prefix_ro_group = QGroupBox(self.tr("Prefix Settings"))
        prefix_ro_form = QFormLayout(prefix_ro_group)
        prefix_ro_form.setLabelAlignment(Qt.AlignLeft)

        self._add_readonly_row(prefix_ro_form, self.tr("Prefix Name"), self.prefix_data.get("name", ""))
        self._add_readonly_row(prefix_ro_form, self.tr("Runner"), self.prefix_data.get("runner", ""))
        self._add_readonly_row(prefix_ro_form, self.tr("Type"), self.prefix_data.get("type", ""))

        codecs = self.prefix_data.get("codecs", "")
        if codecs:
            self._add_readonly_row(prefix_ro_form, self.tr("Codecs"), codecs)

        winetricks = self.prefix_data.get("winetricks", "")
        if winetricks:
            self._add_readonly_row(prefix_ro_form, self.tr("Winetricks"), winetricks)

        fonts = self.prefix_data.get("fonts", False)
        self._add_readonly_row(prefix_ro_form, self.tr("Fonts"), self.tr("Yes") if fonts else self.tr("No"))

        dpi = self.prefix_data.get("dpi", False)
        self._add_readonly_row(prefix_ro_form, self.tr("DPI"), self.tr("Yes") if dpi else self.tr("No"))

        wayland = self.prefix_data.get("wayland", False)
        self._add_readonly_row(prefix_ro_form, self.tr("Wayland Driver"), self.tr("Yes") if wayland else self.tr("No"))

        threetwop = self.prefix_data.get("threetwop", False)
        self._add_readonly_row(prefix_ro_form, self.tr("32 bit prefix"), self.tr("Yes") if threetwop else self.tr("No"))

        content_layout.addWidget(prefix_ro_group)
        content_layout.addStretch()

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_import = QPushButton(self.tr("Import"))
        self.btn_import.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.btn_import.setMinimumWidth(100)
        self.btn_import.clicked.connect(self._on_import_clicked)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_import)
        main_layout.addLayout(btn_layout)

        # Restore previous window size
        self._restore_state()

    def _add_readonly_row(self, form: QFormLayout, label: str, value: str):
        lbl = QLabel(str(value))
        lbl.setStyleSheet(READONLY_STYLE)
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form.addRow(label, lbl)

    def _browse_exe(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle(self.tr("Select Game Executable"))
        current = self.edit_path.text().strip()
        if current:
            dialog.setDirectory(current)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilter("All Files (*);;Executables (*.exe *.sh *.bin)")
        dialog.setViewMode(QFileDialog.Detail)
        if dialog.exec():
            files = dialog.selectedFiles()
            if files:
                self.edit_path.setText(files[0])

    def _on_import_clicked(self):
        """Import logic"""
        name = self.edit_name.text().strip()
        path = self.edit_path.text().strip()

        if not name:
            self.edit_name.setPlaceholderText(self.tr("Name is required"))
            self.edit_name.setFocus()
            return
        if not path:
            self.edit_path.setPlaceholderText(self.tr("Executable path is required"))
            self.edit_path.setFocus()
            return

        data = GameManager.get_game(name)
        if data:
            logger.info("Already exists a game with that name")
            QMessageBox.warning(
                self,
                self.tr("Game Already Exists"),
                self.tr(f"A game named '{name}' already exists in the library.")
            )
            return

        # Apply edits back onto game_data before passing to tasks
        self.game_data["name"] = name
        self.game_data["path"] = path
        self.game_data["vndb"] = self.edit_vndb.text().strip()

        runner_type = self.prefix_data.get("type", "")
        runner_name = self.prefix_data.get("runner", "")
        prefix_name = self.prefix_data.get("name", "")

        if runner_type not in ("proton", "wine"):
            logger.error(f"Unknown runner type '{runner_type}' in import file.")
            return

        base_path = (
            self.user_settings.get(config.USER_CONF_PROTON_RUNNERS_PATH, config.PROTON_RUNNERS_DIR) if runner_type == "proton" 
            else self.user_settings.get(config.USER_CONF_WINE_RUNNERS_PATH, config.WINE_RUNNERS_DIR)
        )
        runner_path = Path(base_path) / runner_name
        runner_exists = RunnerManagerInterface.is_runner_valid(runner_path)

        shared_data = {
            "runner_path": runner_path,
            "downloaded_path": None,
        }

        console = ConsoleDialog(self)
        console.setWindowTitle(self.tr(f"Importing: {name}"))

        # Runner Tasks
        if not runner_exists:
            console.add_task(
                lambda logger: self._task_download_runner(logger, runner_type, runner_name, shared_data),
                {}, f"Downloading runner: {runner_name}"
            )
            console.add_task(
                lambda logger: self._task_extract_runner(logger, runner_type, runner_name, shared_data),
                {}, f"Extracting runner: {runner_name}"
            )
        else:
            console.add_task(
                lambda logger: logger(f"Runner '{runner_name}' already installed, skipping download."),
                {}, "Checking runner"
            )

        # Prefix Tasks
        if PrefixManager.get_prefix_info(prefix_name):
            console.add_task(
                lambda logger: logger(f"Prefix '{prefix_name}' already exists, skipping creation."),
                {}, "Checking prefix"
            )
        else:
            self._setup_prefix_tasks(console, self.prefix_data, runner_type, runner_path)

        # Download covers
        console.add_task(
            lambda logger: self._task_download_assets(logger, self.game_data),
            {}, self.tr("Downloading game artwork")
        )
                    
        # Add game task
        console.add_task(
            lambda logger: self._task_create_game(logger, self.game_data, self.prefix_data),
            {}, f"Registering game: {name}"
        )

        self._import_env_vars()

        self._import_success = False
        console.finished_all.connect(lambda: setattr(self, '_import_success', True))
        console.finished_all.connect(self.import_finished.emit)
        
        console.start_queue()
        console.exec()

        # Closes the Import Game dialog when closing the log dialog
        if getattr(self, '_import_success', False):
            self.accept()

    def _import_env_vars(self):
        """Registers missing env variables from the import"""

        # Fetch env vars from the import
        imported_envvars = self.game_data.get("envvar", {})
        if not imported_envvars:
            return

        # Fetch currently registered variables
        current_vars = self.user_settings.get(config.USER_CONF_ENV_VARIABLE_LIST, [])

        # Map existing keys
        existing_keys = {var.get("key") for var in current_vars if "key" in var}
        
        runner_type = self.prefix_data.get("type", "")
        has_new_vars = False

        for key, value in imported_envvars.items():
            if key not in existing_keys:
                safe_id = key.lower().replace(" ", "_")
                new_var = {
                    "id": safe_id,
                    "name": key,
                    "key": key,
                    "value": value
                }

                current_vars.append(new_var)
                has_new_vars = True
                logger.info(f"Registered global environment variable from import: {key}")

        # Save
        if has_new_vars:
            self.user_settings.set(config.USER_CONF_ENV_VARIABLE_LIST, current_vars)
    
    def _task_download_runner(self, console_logger, runner_type, runner_name, shared_data):
        last_percent = [-1]

        def progress(percent):
            if percent % 5 == 0 and percent != last_percent[0]:
                console_logger(f"[Progress] {percent}% complete...")
                last_percent[0] = percent

        try:
            if runner_type == "proton":
                manager = RunnerManagerProtonGE()
                path = manager.get_runner_download({'tag': runner_name}, progress_callback=progress)
            else:
                parts = runner_name.replace("wine-", "").split("-")
                tag = parts[0]
                arch = "wow64" if "wow64" in runner_name else "amd64"
                release_data = {
                    'tag': tag,
                    'has_wow64': arch == "wow64",
                    'has_amd64': arch == "amd64",
                }
                manager = RunnerManagerKron4ek()
                path = manager.get_runner_download(release_data, arch=arch, progress_callback=progress)

            if not path:
                raise Exception("Download returned no path.")

            shared_data["downloaded_path"] = path
            console_logger(f"Download complete: {path.name}")

        except Exception as e:
            console_logger(f"[FATAL ERROR] Runner download failed: {e}")
            raise

    def _task_extract_runner(self, console_logger, runner_type, runner_name, shared_data):
        path = shared_data.get("downloaded_path")
        if not path or not path.exists():
            raise Exception("No downloaded archive found to extract.")

        dest_dir = self.user_settings.get(config.USER_CONF_PROTON_RUNNERS_PATH, config.PROTON_RUNNERS_DIR) if runner_type == "proton" else self.user_settings.get("WINE_RUNNERS_DIR", config.WINE_RUNNERS_DIR)
        compression = "xz" if path.suffix == ".xz" else "gz"

        console_logger(f"Extracting {path.name}...")
        success = RunnerManagerInterface.extract_tar(path, dest_dir, runner_name, compression=compression)
        if success:
            console_logger("Extraction complete.")
        else:
            raise Exception("Extraction failed.")

    def _setup_prefix_tasks(self, console, prefix_data, runner_type, runner_path):
        """Registers all prefix creation tasks into the console queue."""
        prefix_name = prefix_data.get("name")
        prefix = PrefixManager(prefix_name)

        success = prefix.create_prefix(
            runner_path=str(runner_path),
            codecs=prefix_data.get("codecs", ""),
            winetricks=prefix_data.get("winetricks", ""),
            threetwop=prefix_data.get("threetwop", False),
            executor=console
        )
        if not success:
            logger.error("Failed to prepare prefix creation tasks.")
            return

        if prefix_data.get("fonts", False):
            saved_fonts = self.user_settings.get(config.USER_CONF_FONT_FOLDER, "")
            if saved_fonts:
                prefix.add_fonts(saved_fonts, executor=console)
            else:
                console.add_task(
                    lambda logger: logger("[WARNING] Skipping font symlink. Not configured in Settings."),
                    {}, "Fonts"
                )

        prefix.dpi = prefix_data.get("dpi", False)
        if prefix.dpi:
            prefix.set_prefix_dpi(executor=console)

        prefix.wayland_driver = prefix_data.get("wayland", False)
        if prefix.wayland_driver:
            prefix.enable_wayland_driver(executor=console)

        if runner_type == "wine":
            prefix.install_dxvk(executor=console)

    def _task_create_game(self, console_logger, game_data, prefix_data):
        """call GameManager to register the game"""
        name = game_data.get("name")
        path = game_data.get("path")
        prefix = prefix_data.get("name")
        vndb = game_data.get("vndb", "")

        console_logger(f"Creating game entry for '{name}'...")

        # Build the GameCard from imported data so all fields are preserved
        card = GameCard.from_dict(name, game_data)
        GameManager.add_game(
            exe=path,
            name=name,
            prefix=prefix,
            vndb=vndb
        )

        if self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False) and self.savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_ALL_GAMES, False):
            card.gdrive = True

        # Persist extra fields
        GameManager.update_game(name, card.to_dict())
        console_logger(f"Game '{name}' registered successfully.")

    def _task_download_assets(self, console_logger, game_data):
        """Downloads external cover and layout artwork if URLs are present."""
        covers_dir = Path(self.user_settings.get(config.USER_CONF_COVERS_PATH, config.COVERS_DIR))

        assets_to_download = [
            ("cover_source_url", "cover_path", "Cover"),
            ("layout_source_url", "layout_path", "Layout")
        ]

        for url_key, path_key, label in assets_to_download:
            url = game_data.get(url_key)
            if not url or not url.strip():
                continue

            console_logger(f"Downloading game {label.lower()} from URL...")
            try:
                # Extract filename from URL safely
                parsed_url = urllib.parse.urlparse(url)
                filename = Path(parsed_url.path).name
                target_path = covers_dir / filename

                # Request image
                response = requests.get(url, timeout=5)
                response.raise_for_status()

                # Save image file
                with open(target_path, "wb") as f:
                    f.write(response.content)

                # Save the covers paths
                game_data[path_key] = str(target_path)
                console_logger(f"Successfully saved {label.lower()} to: {filename}")

            except Exception as e:
                # Catching exceptions ensures the import queue keeps moving even if downloading fails
                console_logger(f"[WARNING] Could not download {label.lower()}: {e}. Skipping artwork...")
                logger.warning(f"Failed to download artwork asset ({label}) from {url}: {e}")

    def _on_autocomplete_selected(self, vn_data: dict):
        """Updates the VNDB input when an autocomplete result is clicked."""
        self.edit_vndb.setText(vn_data.get("id", ""))

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("ImportGameDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("ImportGameDialog/geometry", self.saveGeometry())
        super().closeEvent(event)
    
    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("ImportGameDialog/geometry", self.saveGeometry())
        super().hideEvent(event)
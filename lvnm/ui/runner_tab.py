import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTabWidget, QGroupBox, QListWidget, QPushButton, 
    QDialog, QMessageBox, QProgressBar, QApplication
)
from PySide6.QtCore import Qt
from runner_manager_kron4ek import RunnerManagerKron4ek
from runner_manager_protonge import RunnerManagerProtonGE
from runner_manager import RunnerManagerInterface
from prefix_manager import PrefixManager
from ui.console_dialog import ConsoleDialog

logger = logging.getLogger(__name__)

class DownloadDialog(QDialog):
    """Popup to list available releases from GitHub"""
    def __init__(self, manager, runner_type, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.runner_type = runner_type # "wine" or "proton"
        self.current_page = 1
        self.releases = []
        
        self.setWindowTitle(self.tr("Download New Runner"))
        self.resize(400, 500)
        
        layout = QVBoxLayout(self)

        # List
        layout.addWidget(QLabel(self.tr("Select a version to download:")))
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        
        # Pagination
        page_layout = QHBoxLayout()
        self.prev_btn = QPushButton(self.tr("← Previous"))
        self.page_label = QLabel(self.tr(f"Page {self.current_page}"))
        self.page_label.setAlignment(Qt.AlignCenter)
        self.next_btn = QPushButton(self.tr("Next →"))
        
        self.prev_btn.clicked.connect(self.load_prev_page)
        self.next_btn.clicked.connect(self.load_next_page)
        
        page_layout.addWidget(self.prev_btn)
        page_layout.addWidget(self.page_label, 1)
        page_layout.addWidget(self.next_btn)
        layout.addLayout(page_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.download_btn = QPushButton(self.tr("Download"))
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        
        self.download_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.download_btn)
        layout.addLayout(btn_layout)

        self.fetch_page()

    def fetch_page(self):
        """Fetches and populates the list for the current page"""
        self.list_widget.clear()
        self.page_label.setText(self.tr(f"Page {self.current_page}"))
        self.prev_btn.setEnabled(self.current_page > 1)
        
        # Update UI while fetching
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.releases = self.manager.get_runner_all_releases(page=self.current_page)
        QApplication.restoreOverrideCursor()

        if not self.releases:
            self.list_widget.addItem(self.tr("No more releases found."))
            self.next_btn.setEnabled(False)
            return
        
        self.next_btn.setEnabled(True)
        for rel in self.releases:
            if self.runner_type == "wine":
                if rel.get("has_amd64"):
                    self.list_widget.addItem(f"{rel['tag']} (amd64)")
                if rel.get("has_wow64"):
                    self.list_widget.addItem(f"{rel['tag']} (wow64)")
            else:
                self.list_widget.addItem(rel['tag'])

    def load_next_page(self):
        self.current_page += 1
        self.fetch_page()

    def load_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.fetch_page()

    def get_selection(self):
        item = self.list_widget.currentItem()
        if not item or not self.releases: return None, None
        
        text = item.text()
        try:
            if self.runner_type == "wine":
                tag = text.split(" (")[0]
                arch = "amd64" if "(amd64)" in text else "wow64"
                rel_data = next(r for r in self.releases if r['tag'] == tag)
                return rel_data, arch
            else:
                rel_data = next(r for r in self.releases if r['tag'] == text)
                return rel_data, None
        except StopIteration:
            return None, None

class RunnerSubTab(QWidget):
    """Reusable component for both Wine and Proton tabs"""
    def __init__(self, manager, base_dir, runner_type):
        super().__init__()
        self.manager = manager
        self.base_dir = base_dir
        self.runner_type = runner_type
        self.get_prefixes_func = PrefixManager.get_prefix_json
        
        layout = QVBoxLayout(self)
        
        # GroupBox for installed runners
        self.group = QGroupBox(self.tr(f"Installed {runner_type.capitalize()} Runners"))
        group_layout = QVBoxLayout(self.group)
        
        self.list_widget = QListWidget()
        group_layout.addWidget(self.list_widget)
        layout.addWidget(self.group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton(self.tr("Add New"))
        self.del_btn = QPushButton(self.tr("Delete Selected"))
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.del_btn)
        layout.addLayout(btn_layout)
        
        # Signals
        self.add_btn.clicked.connect(self.on_add)
        self.del_btn.clicked.connect(self.on_delete)
        
        self.refresh_list()

    def refresh_list(self):
        self.list_widget.clear()
        prefixes_data = PrefixManager.get_prefix_json()
        runners = RunnerManagerInterface.get_local_runners(self.base_dir, prefixes_data)
        self.list_widget.addItems(runners)

    def on_add(self):
        dialog = DownloadDialog(self.manager, self.runner_type, self)
        if dialog.exec():
            rel_data, arch = dialog.get_selection()
            if rel_data:
                try:
                    console = ConsoleDialog(self)
                    console.setWindowTitle(self.tr(f"Installing {self.runner_type.capitalize()}: {rel_data['tag']}"))

                    shared_data = {"downloaded_path": None}
                    # Create Download Task
                    download_task = lambda logger: self._task_download(logger, rel_data, arch, shared_data)
                    # Create Extract Task
                    extract_task = lambda logger: self._task_extract(logger, rel_data, shared_data)

                    # Add the task to the queue
                    console.add_task(download_task, {}, f"Downloading Version {rel_data['tag']}")
                    console.add_task(extract_task, {}, "Extracting runner")
                    
                    # Connect refresh to finish and start queue
                    console.finished_all.connect(self.refresh_list)
                    console.start_queue()
                    console.exec()
                except RuntimeError as e:
                    QMessageBox.critical(
                        self,
                        self.tr("Error"),
                        self.tr(str(e))
                    )

    def _task_download(self, console_logger, rel_data, arch, shared_data):
        """Handles the download runner logic."""
        last_percent = -1

        def internal_progress(percent):
            nonlocal last_percent
            if percent % 5 == 0 and percent != last_percent:
                console_logger(f"[Progress] {percent}% complete...")
                last_percent = percent

        try:
            console_logger(f"Initiating download for version {rel_data['tag']}...")
            
            if self.runner_type == "wine":
                result_path = self.manager.get_runner_download(
                    rel_data, 
                    arch, 
                    progress_callback=internal_progress
                )
            else:
                result_path = self.manager.get_runner_download(
                    rel_data, 
                    progress_callback=internal_progress
                )
            
            if result_path:
                shared_data["downloaded_path"] = result_path
            else:
                raise Exception("Download failed or returned no path.")
            
            console_logger(f"Download finished.")
        except Exception as e:
            console_logger(f"\nFATAL ERROR {str(e)}")
            logger.error(f"Installation error: {e}", exc_info=True)
            raise RuntimeError(f"Installation failed: {e}")

    def _task_extract(self, console_logger, rel_data, shared_data):
        path = shared_data.get("downloaded_path")
        if not path or not path.exists():
            raise Exception("No downloaded file found to extract.")

        console_logger(f"Extracting {path.name}...")
        
        # Determine compression from file extension
        ext = "xz" if path.suffix == ".xz" else "gz"
        
        # Call Manager to extract
        success = self.manager.extract_tar(
            path, 
            self.base_dir, 
            rel_data['tag'], 
            compression=ext
        )
        
        if success:
            console_logger("\nExtraction complete.")
        else:
            raise Exception("Extraction failed.")
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
        QApplication.processEvents()

    def on_delete(self):
        current = self.list_widget.currentItem()
        if not current: return
        
        # Select runner name without prefixes attached
        folder = current.text().split(" (")[0]
        confirm = QMessageBox.question(self, self.tr("Delete?"), 
                                     f"{self.tr('Delete runner')} {folder}?")
        
        if confirm == QMessageBox.Yes:
            try:
                RunnerManagerInterface.delete_runner(self.base_dir, folder)
                self.refresh_list()
            except RuntimeError as e:
                QMessageBox.critical(
                    self,
                    self.tr("Error"),
                    self.tr(str(e))
                )

class RunnerTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        
        # Instantiate managers
        self.wine_manager = RunnerManagerKron4ek()
        self.proton_manager = RunnerManagerProtonGE()
        
        # Add sub-tabs
        self.tabs.addTab(RunnerSubTab(self.wine_manager, self.wine_manager.WINE_RUNNERS_PATH, "wine"), "Wine")
        self.tabs.addTab(RunnerSubTab(self.proton_manager, self.proton_manager.PROTON_RUNNER_DIR, "proton"), "Proton")

        self.tabs.currentChanged.connect(self.refresh_active_tab)
        
        layout.addWidget(self.tabs)

    def refresh_active_tab(self):
        """Forces the currently visible sub-tab to reload its data"""
        current_widget = self.tabs.currentWidget()
        if current_widget:
            current_widget.refresh_list()
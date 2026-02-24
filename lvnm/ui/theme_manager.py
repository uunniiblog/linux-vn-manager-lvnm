from PySide6.QtGui import QGuiApplication, Qt
from PySide6.QtWidgets import QApplication

class ThemeManager:

    BASE_STYLE = """
    QMainWindow {{
        background-color: {bg_main};
        color: {text_main};
    }}
    QListWidget#sidebar {{
        background-color: {bg_sidebar};
        color: {text_sidebar};
        border: none;
        outline: none;
    }}
    QListWidget#sidebar::item {{
        padding: 15px 20px;
    }}
    QListWidget#sidebar::item:selected {{
        background-color: {bg_sidebar_sel};
        color: {text_highlight};
        border-left: 3px solid {accent};
    }}
    QSplitter::handle {{
        background-color: {splitter};
    }}
    QLabel {{
        color: {text_main};
    }}
    
    /* --- SETTINGS SECTIONS --- */
    QGroupBox {{
        border: 1px solid {border_color};
        border-radius: 6px;
        margin-top: 15px; /* Leaves space for the title text */
        padding-top: 15px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        left: 10px;
        color: {accent}; /* Makes the section titles blue */
        font-weight: bold;
    }}
    """

    PALETTES = {
        "dark": {
            "bg_main": "#1e1e1e",
            "bg_sidebar": "#252526",
            "bg_sidebar_sel": "#37373d",
            "text_main": "#cccccc",
            "text_sidebar": "#cccccc",
            "text_highlight": "#ffffff",
            "accent": "#0078d4",
            "splitter": "#333333",
            "border_color": "#3f3f46" # NEW: Subtle gray border for dark mode
        },
        "light": {
            "bg_main": "#ffffff",
            "bg_sidebar": "#f3f3f3",
            "bg_sidebar_sel": "#eaeaea",
            "text_main": "#333333",
            "text_sidebar": "#616161",
            "text_highlight": "#000000",
            "accent": "#005a9e",
            "splitter": "#d2d2d2",
            "border_color": "#e5e5e5" # NEW: Subtle gray border for light mode
        }
    }

    def __init__(self, settings):
        self.settings = settings
        # Connect to system changes
        QGuiApplication.styleHints().colorSchemeChanged.connect(self.update_theme)

    def is_dark(self):
        mode = self.settings.value("theme_mode", "auto")
        if mode == "auto":
            return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        return mode == "dark"

    def update_theme(self):
        palette_key = "dark" if self.is_dark() else "light"
        colors = self.PALETTES[palette_key]
        
        # Format the stylesheet correctly
        full_qss = self.BASE_STYLE.format(**colors)
        
        # Apply to the WHOLE application
        QApplication.instance().setStyleSheet(full_qss)

        # Re-apply sidebar font override after stylesheet resets it
        # if hasattr(self, '_sidebar_font_override'):
        #     self._sidebar_font_override()

        from ui.main_window import MainWindow
        for widget in QApplication.instance().topLevelWidgets():
            if isinstance(widget, MainWindow):
                widget.update_sidebar_font()
                break

    def get_theme_mode(self):
        """Returns 'light', 'dark', or 'auto' based on settings."""
        # This matches what SettingsTab is looking for
        return self.settings.value("theme_mode", "auto")
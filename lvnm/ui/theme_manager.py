from PySide6.QtGui import QGuiApplication, Qt
from PySide6.QtWidgets import QApplication

class ThemeManager:

    BASE_STYLE = """
    /* ── Root surfaces ─────────────────────────────────────────── */
    QMainWindow, QDialog, QScrollArea, QFrame#sidebar_container {{
        background-color: {bg_main};
        color: {text_main};
    }}

    /* Global widget text color. We removed the global transparent background to fix Dialogs! */
    QWidget {{
        color: {text_main};
    }}
    
    /* Ensure specific inputs remain opaque */
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QPushButton {{
        background-color: {bg_input};
    }}

    /* ── Left sidebar ───────────────────────────────────────────── */
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

    /* ── Splitter ───────────────────────────────────────────────── */
    QSplitter::handle {{
        background-color: {splitter};
    }}

    /* ── Labels ─────────────────────────────────────────────────── */
    QLabel {{
        background-color: transparent;
        color: {text_main};
    }}

    /* ── Group boxes ────────────────────────────────────────────── */
    QGroupBox {{
        border: 1px solid {border_color};
        border-radius: 6px;
        margin-top: 15px;
        padding-top: 15px;
        background-color: {bg_main};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        left: 10px;
        color: {accent};
        font-weight: bold;
        background-color: transparent;
    }}

    /* ── Text inputs ────────────────────────────────────────────── */
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {bg_input};
        color: {text_main};
        border: 1px solid {border_color};
        border-radius: 4px;
        padding: 3px 6px;
        selection-background-color: {accent};
        selection-color: #ffffff;
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {accent};
    }}
    QLineEdit:disabled, QTextEdit:disabled {{
        background-color: {bg_disabled};
        color: {text_disabled};
    }}

    /* ── Combo boxes ────────────────────────────────────────────── */
    QComboBox {{
        background-color: {bg_input};
        color: {text_main};
        border: 1px solid {border_color};
        border-radius: 4px;
        padding: 3px 6px;
        min-height: 22px;
    }}
    QComboBox:focus {{
        border: 1px solid {accent};
    }}
    QComboBox:disabled {{
        background-color: {bg_disabled};
        color: {text_disabled};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 6px solid {text_main};
        width: 0;
        height: 0;
        margin-right: 4px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {bg_popup};
        color: {text_main};
        border: 1px solid {border_color};
        selection-background-color: {accent};
        selection-color: #ffffff;
        outline: none;
    }}

    /* ── Buttons ────────────────────────────────────────────────── */
    QPushButton {{
        background-color: {bg_button};
        color: {text_button};
        border: 1px solid {border_color};
        border-radius: 4px;
        padding: 5px 14px;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background-color: {bg_button_hover};
        border-color: {accent};
    }}
    QPushButton:pressed {{
        background-color: {bg_button_pressed};
    }}
    QPushButton:disabled {{
        background-color: {bg_disabled};
        color: {text_disabled};
        border-color: {border_color};
    }}

    /* ── Checkboxes ─────────────────────────────────────────────── */
    QCheckBox {{
        color: {text_main};
        background-color: transparent;
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {border_color};
        border-radius: 3px;
        background-color: {bg_input};
    }}
    QCheckBox::indicator:checked {{
        background-color: {accent};
        border-color: {accent};
    }}
    QCheckBox::indicator:disabled {{
        background-color: {bg_disabled};
        border-color: {border_color};
    }}

    /* ── Scroll areas ───────────────────────────────────────────── */
    QScrollArea {{
        background-color: {bg_main};
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background-color: {bg_main};
    }}

    /* ── Scroll bars ────────────────────────────────────────────── */
    QScrollBar:vertical {{
        background-color: {bg_scrollbar_track};
        width: 10px;
        border-radius: 5px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background-color: {bg_scrollbar_handle};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {accent};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background-color: {bg_scrollbar_track};
        height: 10px;
        border-radius: 5px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {bg_scrollbar_handle};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {accent};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ── Frames / panels (GameSidebar uses QFrame) ──────────────── */
    QFrame {{
        background-color: {bg_main};
        color: {text_main};
    }}
    QFrame[frameShape="4"],   /* HLine */
    QFrame[frameShape="5"] {{ /* VLine */
        background-color: {border_color};
    }}

    /* ── Tab bar (if used anywhere) ─────────────────────────────── */
    QTabWidget::pane {{
        border: 1px solid {border_color};
        background-color: {bg_main};
    }}
    QTabBar::tab {{
        background-color: {bg_button};
        color: {text_main};
        border: 1px solid {border_color};
        padding: 5px 12px;
    }}
    QTabBar::tab:selected {{
        background-color: {bg_main};
        border-bottom: 2px solid {accent};
        color: {accent};
    }}

    /* ── Tooltips ───────────────────────────────────────────────── */
    QToolTip {{
        background-color: {bg_popup};
        color: {text_main};
        border: 1px solid {border_color};
        padding: 4px;
    }}

    /* ── Menu bar / menus ───────────────────────────────────────── */
    QMenuBar {{
        background-color: {bg_main};
        color: {text_main};
    }}
    QMenuBar::item:selected {{
        background-color: {bg_item_hover};
    }}
    QMenu {{
        background-color: {bg_popup};
        color: {text_main};
        border: 1px solid {border_color};
    }}
    QMenu::item:selected {{
        background-color: {accent};
        color: #ffffff;
    }}

    /* ── Message boxes ──────────────────────────────────────────── */
    QMessageBox {{
        background-color: {bg_main};
        color: {text_main};
    }}
    
    """

    GAME_LIST_ITEM_QSS = """
    QListWidget::item:selected QLabel#gameItemCover {{
        border-color: rgba(255, 255, 255, 0.3);
    }}

    GameListItem[hovered="true"] {{
        background-color: rgba(255, 255, 255, 18);
    }}

    /* Ensure children don't fight the background */
    GameListItem QLabel {{
        background-color: transparent;
    }}

    """

    PALETTES = {
        "dark": {
            "bg_main":              "#1e1e1e",
            "bg_sidebar":           "#252526",
            "bg_sidebar_sel":       "#37373d",
            "bg_input":             "#3c3c3c",
            "bg_button":            "#3c3c3c",
            "bg_button_hover":      "#505050",
            "bg_button_pressed":    "#2a2a2a",
            "bg_disabled":          "#2d2d2d",
            "bg_list":              "#252526",
            "bg_item_hover":        "#2a2d2e",
            "bg_popup":             "#2d2d30",
            "bg_scrollbar_track":   "#2a2a2a",
            "bg_scrollbar_handle":  "#555555",
            "text_main":            "#cccccc",
            "text_sidebar":         "#cccccc",
            "text_highlight":       "#ffffff",
            "text_button":          "#cccccc",
            "text_disabled":        "#666666",
            "accent":               "#0078d4",
            "splitter":             "#333333",
            "border_color":         "#3f3f46",
            "bg_item_cover":        "#2a2a2a",
            "text_muted":           "#888888",
             "text_subtle":         "#666666",
        },
        "light": {
            "bg_main":              "#ffffff",
            "bg_sidebar":           "#f3f3f3",
            "bg_sidebar_sel":       "#eaeaea",
            "bg_input":             "#ffffff",
            "bg_button":            "#e8e8e8",
            "bg_button_hover":      "#d4d4d4",
            "bg_button_pressed":    "#c8c8c8",
            "bg_disabled":          "#f0f0f0",
            "bg_list":              "#ffffff",
            "bg_item_hover":        "#f0f0f0",
            "bg_popup":             "#ffffff",
            "bg_scrollbar_track":   "#f0f0f0",
            "bg_scrollbar_handle":  "#c0c0c0",
            "text_main":            "#1e1e1e",
            "text_sidebar":         "#616161",
            "text_highlight":       "#000000",
            "text_button":          "#1e1e1e",
            "text_disabled":        "#a0a0a0",
            "accent":               "#005a9e",
            "splitter":             "#d2d2d2",
            "border_color":         "#d0d0d0",
            "bg_item_cover":        "#e0e0e0",
            "text_muted":           "#666666",
            "text_subtle":          "#999999",
        },
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
        full_qss = (self.BASE_STYLE + self.GAME_LIST_ITEM_QSS).format(**colors)
        
        # Apply to the WHOLE application
        QApplication.instance().setStyleSheet(full_qss)

        from ui.main_window import MainWindow
        for widget in QApplication.instance().topLevelWidgets():
            if isinstance(widget, MainWindow):
                widget.update_sidebar_font()
                break

    def get_theme_mode(self):
        """Returns 'light', 'dark', or 'auto' based on settings."""
        return self.settings.value("theme_mode", "auto")
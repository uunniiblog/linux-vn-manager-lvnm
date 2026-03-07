from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                               QPushButton, QLabel, QTabWidget, QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
from datetime import datetime
import logging
logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)
from timetracker.log_manager import LogManager
import config

# Configure Japanese/CJK support
matplotlib.rcParams['font.sans-serif'] = [
    'Noto Sans CJK JP', 'WenQuanYi Micro Hei', 'IPAexGothic', 
    'Droid Sans Fallback', 'DejaVu Sans', 'sans-serif'
]
matplotlib.rcParams['axes.unicode_minus'] = False

class StatsTab(QWidget):
    def __init__(self, theme_manager=None):
        super().__init__()
        self.theme_manager = theme_manager
        self.theme_manager.theme_changed.connect(self.refresh_data)
        self.log_manager = LogManager(config.LOG_DIR)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        
        self.setup_individual_tab()
        self.setup_global_tab()
        self.refresh_data()

    def get_theme_colors(self):
        """Fetches colors from your ThemeManager or defaults based on lightness."""
        is_dark = self.theme_manager.is_dark() or False          

        if is_dark:
            return {
                'bg': "#1e1e1e",
                'text': "#cccccc",
                'border': "#3f3f46",
                'accent': "#3498db",
                'accent_global': "#e67e22",
                'highlight': "#f1c40f",
                'muted': "#888888"
            }
        else:
            return {
                'bg': "#ffffff",
                'text': "#1e1e1e",
                'border': "#d0d0d0",
                'accent': "#005a9e",
                'accent_global': "#d35400",
                'highlight': "#005a9e",
                'muted': "#666666"
            }

    def setup_individual_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        controls = QHBoxLayout()
        self.app_combo = QComboBox()
        self.app_combo.currentIndexChanged.connect(self.update_graph)
        controls.addWidget(self.app_combo, stretch=1)

        refresh_btn = QPushButton()
        refresh_btn.setIcon(QIcon.fromTheme("view-refresh"))
        refresh_btn.setFixedSize(30, 30)
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.setStyleSheet("""
            QPushButton#refreshBtn {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            QPushButton#refreshBtn:hover {
                background-color: #505050;
                border-color: #777777;
            }
            QPushButton#refreshBtn:pressed {
                background-color: #2a2a2a;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_data)
        controls.addWidget(refresh_btn)
        layout.addLayout(controls)

        self.info_label = QLabel("Total Playtime: 0h 0m")
        self.info_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.info_label)

        self.figure, self.ax = plt.subplots(figsize=(5, 3))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas, stretch=1)
        
        self.tabs.addTab(tab, self.tr("Individual App"))

    def setup_global_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(self.tr("Timeframe:")))
        self.range_combo = QComboBox()
        self.range_combo.addItems([self.tr("Today"), self.tr("Last 7 Days"), self.tr("Last 30 Days"), self.tr("All Time")])
        self.range_combo.currentIndexChanged.connect(self.update_global_stats)
        controls.addWidget(self.range_combo, stretch=1)
        layout.addLayout(controls)

        self.summary_info = QLabel(self.tr("Total time in period: 0h 0m"))
        self.summary_info.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.summary_info)

        self.global_figure, self.global_ax = plt.subplots(figsize=(6, 4))
        self.global_canvas = FigureCanvas(self.global_figure)
        layout.addWidget(self.global_canvas, stretch=1)

        self.tabs.addTab(tab, self.tr("Global Summary"))

    def render_canvas(self, daily_data):
        colors = self.get_theme_colors()
        
        self.ax.clear()
        self.figure.patch.set_facecolor(colors['bg'])
        self.ax.set_facecolor(colors['bg'])
        
        self.ax.tick_params(axis='both', colors=colors['text'], labelsize=8)
        self.ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{x:.1f}h"))
        
        for spine in self.ax.spines.values():
            spine.set_color(colors['border'])

        self.info_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {colors['accent']};")

        if daily_data:
            sorted_dates = sorted(daily_data.keys())
            plot_hours = [daily_data[d] for d in sorted_dates]
            self.ax.bar(sorted_dates, plot_hours, color=colors['accent'], width=0.6)
            
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            self.ax.xaxis.set_major_locator(mdates.DayLocator())
            self.figure.autofmt_xdate()
        else:
            self.ax.text(0.5, 0.5, self.tr("No data available"), color=colors['muted'], 
                         ha='center', va='center', transform=self.ax.transAxes)

        self.canvas.draw()

    def render_global_canvas(self, labels, hours):
        colors = self.get_theme_colors()
        
        self.global_ax.clear()
        self.global_figure.patch.set_facecolor(colors['bg'])
        self.global_ax.set_facecolor(colors['bg'])

        self.summary_info.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {colors['accent_global']};")
        
        if labels:
            bars = self.global_ax.barh(labels, hours, color=colors['accent_global'], height=0.7)
            
            for bar in bars:
                width = bar.get_width()
                self.global_ax.text(width + 0.05, bar.get_y() + bar.get_height()/2, 
                                    f' {width:.1f}h', 
                                    va='center', color=colors['highlight'], fontsize=10, fontweight='bold')

            max_h = max(hours) if hours else 1
            self.global_ax.set_xlim(0, max_h * 1.25)
            
            self.global_ax.tick_params(axis='y', colors=colors['text'], labelsize=8)
            self.global_ax.tick_params(axis='x', colors=colors['muted'], labelsize=8)
            self.global_figure.subplots_adjust(left=0.4, right=0.95, top=0.95, bottom=0.1)
        else:
             self.global_ax.text(0.5, 0.5, self.tr("No data available"), color=colors['muted'], 
                         ha='center', va='center', transform=self.global_ax.transAxes)
        
        self.global_canvas.draw()

    def refresh_data(self):
        self.app_combo.blockSignals(True)
        self.app_combo.clear()
        apps = self.log_manager.get_apps_sorted_by_latest()
        if apps:
            self.app_combo.addItems(apps)
            self.app_combo.setCurrentIndex(0)
        self.app_combo.blockSignals(False)
        self.update_graph()
        self.update_global_stats()

    def update_graph(self):
        app = self.app_combo.currentText()
        if not app:
            self.render_canvas({})
            return
        total_seconds, daily_data = self.log_manager.get_stats_for_app(app)
        h, m = int(total_seconds // 3600), int((total_seconds % 3600) // 60)
        self.info_label.setText(self.tr(f"Total Playtime: {h}h {m}m"))
        self.render_canvas(daily_data)

    def update_global_stats(self):
        current_text = self.range_combo.currentText()
        timeframe = "All Time"
        if current_text == self.tr("Today"): timeframe = "Today"
        elif current_text == self.tr("Last 7 Days"): timeframe = "Last 7 Days"
        elif current_text == self.tr("Last 30 Days"): timeframe = "Last 30 Days"

        data = self.log_manager.get_global_summary(timeframe)
        total_seconds = sum(item[1] for item in data)
        h, m = int(total_seconds // 3600), int((total_seconds % 3600) // 60)
        self.summary_info.setText(self.tr(f"Total time in period: {h}h {m}m"))

        top_data = data[:15]
        top_data.reverse()
        display_labels = []
        for app, seconds, title in top_data:
            clean_title = title.split(' — ')[0] if ' — ' in title else title
            if len(clean_title) > 30: clean_title = clean_title[:27] + "..."
            display_labels.append(f"{app.upper()}\n({clean_title})")

        hours = [item[1] / 3600 for item in top_data]
        self.render_global_canvas(display_labels, hours)
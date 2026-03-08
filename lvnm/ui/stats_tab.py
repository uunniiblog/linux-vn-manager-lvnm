from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
                               QPushButton, QLabel, QTabWidget, QToolTip)
from PySide6.QtCharts import (QChart, QChartView, QBarSeries, QBarSet,
                               QBarCategoryAxis, QValueAxis,
                               QHorizontalBarSeries)
from PySide6.QtGui import QIcon, QColor, QPainter, QFont, QCursor
from PySide6.QtCore import Qt

from timetracker.log_manager import LogManager
import config


class StatsTab(QWidget):
    def __init__(self, theme_manager=None):
        super().__init__()
        self.theme_manager = theme_manager
        if self.theme_manager:
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
        is_dark = self.theme_manager.is_dark() if self.theme_manager else True
        if is_dark:
            return {
                'bg': QColor("#1e1e1e"),
                'text': QColor("#cccccc"),
                'border': QColor("#3f3f46"),
                'accent': QColor("#3498db"),
                'accent_global': QColor("#e67e22"),
                'highlight': QColor("#f1c40f"),
                'muted': QColor("#888888"),
                'grid': QColor("#2d2d2d"),
            }
        else:
            return {
                'bg': QColor("#ffffff"),
                'text': QColor("#1e1e1e"),
                'border': QColor("#d0d0d0"),
                'accent': QColor("#005a9e"),
                'accent_global': QColor("#d35400"),
                'highlight': QColor("#005a9e"),
                'muted': QColor("#666666"),
                'grid': QColor("#eeeeee"),
            }

    def _style_chart(self, chart):
        """Apply theme colors to a QChart."""
        colors = self.get_theme_colors()
        chart.setBackgroundBrush(colors['bg'])
        chart.setBackgroundRoundness(0)
        chart.setPlotAreaBackgroundBrush(colors['bg'])
        chart.setPlotAreaBackgroundVisible(True)

        title_font = QFont()
        title_font.setPointSize(9)
        chart.setTitleFont(title_font)
        chart.setTitleBrush(colors['text'])
        chart.legend().setVisible(False)

    def _style_axis(self, axis, colors):
        """Apply theme colors to any QAbstractAxis."""
        axis.setLabelsBrush(colors['text'])
        axis.setLinePen(colors['border'])
        axis.setGridLinePen(colors['grid'])
        labels_font = QFont()
        labels_font.setPointSize(8)
        axis.setLabelsFont(labels_font)

    def setup_individual_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        controls = QHBoxLayout()
        self.app_combo = QComboBox()
        self.app_combo.currentIndexChanged.connect(self.update_graph)
        controls.addWidget(self.app_combo, stretch=1)

        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(QIcon.fromTheme("view-refresh"))
        self.refresh_btn.setFixedSize(30, 30)
        self.refresh_btn.setObjectName("refreshBtn")
        self.refresh_btn.setStyleSheet("""
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
        self.refresh_btn.clicked.connect(self.refresh_data)
        controls.addWidget(self.refresh_btn)
        layout.addLayout(controls)

        self.info_label = QLabel("Total Playtime: 0h 0m")
        self.info_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.info_label)

        self.ind_chart = QChart()
        self.ind_chart.setMargins(__import__('PySide6.QtCore', fromlist=['QMargins']).QMargins(10, 10, 10, 10))
        self.ind_chart_view = QChartView(self.ind_chart)
        self.ind_chart_view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.ind_chart_view, stretch=1)

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

        self.global_chart = QChart()
        self.global_chart.setMargins(__import__('PySide6.QtCore', fromlist=['QMargins']).QMargins(10, 10, 10, 10))
        self.global_chart_view = QChartView(self.global_chart)
        self.global_chart_view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.global_chart_view, stretch=1)

        self.tabs.addTab(tab, self.tr("Global Summary"))

    def render_canvas(self, daily_data):
        colors = self.get_theme_colors()
        chart = self.ind_chart
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)

        self._style_chart(chart)
        self.info_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {colors['accent'].name()};")

        if not daily_data:
            chart.setTitle(self.tr("No data available"))
            return

        chart.setTitle("")
        sorted_dates = sorted(daily_data.keys())
        bar_set = QBarSet("")
        bar_set.setColor(colors['accent'])
        bar_set.setBorderColor(colors['accent'])

        for d in sorted_dates:
            bar_set.append(daily_data[d])

        series = QBarSeries()
        series.append(bar_set)
        series.setBarWidth(0.6)
        chart.addSeries(series)

        # X axis - dates
        categories = [d.strftime('%b %d') for d in sorted_dates]
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        self._style_axis(axis_x, colors)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        # Y axis - hours
        max_h = max(daily_data.values()) if daily_data else 1
        axis_y = QValueAxis()
        axis_y.setRange(0, max_h * 1.15)
        axis_y.setLabelFormat("%.1fh")
        self._style_axis(axis_y, colors)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

    def render_global_canvas(self, labels, hours, full_titles):
        colors = self.get_theme_colors()
        chart = self.global_chart
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)

        self._style_chart(chart)
        self.summary_info.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {colors['accent_global'].name()};")

        if not labels:
            chart.setTitle(self.tr("No data available"))
            return

        chart.setTitle("")
        bar_set = QBarSet("")
        bar_set.setColor(colors['accent_global'])
        bar_set.setBorderColor(colors['accent_global'])
        for h in hours:
            bar_set.append(h)

        series = QHorizontalBarSeries()
        series.append(bar_set)
        series.setBarWidth(0.7)
        chart.addSeries(series)

        # Tooltip
        self._full_titles = full_titles
        series.hovered.connect(self.show_tooltip)

        # Y axis - app labels
        axis_y = QBarCategoryAxis()
        axis_y.append(labels)
        self._style_axis(axis_y, colors)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        # X axis - hours
        max_h = max(hours) if hours else 1
        axis_x = QValueAxis()
        axis_x.setRange(0, max_h * 1.25)
        axis_x.setLabelFormat("%.1fh")
        self._style_axis(axis_x, colors)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

    def show_tooltip(self, status, index):
        if status:
            label = self._full_titles[index]
            # Show tooltip at the current mouse position
            QToolTip.showText(QCursor.pos(), label, self.global_chart_view)
        else:
            QToolTip.hideText()

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
        full_titles = [] # tooltip
        hours = []

        for app, seconds, title in top_data:
            clean_title = title.split(' — ')[0] if ' — ' in title else title
            full_titles.append(f"{app.upper()}\n{clean_title}")
            
            # Truncate
            if len(clean_title) > 25:
                display_title = clean_title[:22] + "..."
            else:
                display_title = clean_title
            
            display_labels.append(f"{app.upper()} ({display_title})")
            hours.append(seconds / 3600)

        self.render_global_canvas(display_labels, hours, full_titles)
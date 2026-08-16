"""
RetailFlow POS - Financial Trend Timeline Chart Widget
High-performance PySide6.QtCharts time-series visualization for executive financial reporting.
Visualizes Net Sales, Gross Profit, Store OPEX, and Net Operating Profit with adaptive date labeling,
zero baseline rendering, point markers, interactive legend toggles, and consolidated hover tooltips.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from PySide6.QtCore import QMargins, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtCharts import (
    QCategoryAxis,
    QChart,
    QChartView,
    QLegendMarker,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from application.dto.report_dto import DailyFinancialPointDTO


class FinancialTrendChartWidget(QFrame):
    """
    Financial trend timeline chart component powered by PySide6.QtCharts.
    Visualizes Net Sales, Gross Profit, Store OPEX, and Net Operating Profit.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._daily_points: List[DailyFinancialPointDTO] = []
        self._is_all_zero = True

        self.setObjectName("financialTrendChartCard")
        self.setStyleSheet("""
            QFrame#financialTrendChartCard {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        # ── 1. Header Row (Title + Hover Info Tooltip Banner) ──
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(12)

        self._title_lbl = QLabel("Financial Trend Timeline")
        self._title_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        hdr_row.addWidget(self._title_lbl)

        hdr_row.addStretch(1)

        # Hover details banner
        self._hover_info_lbl = QLabel("Hover over data points to inspect daily totals")
        self._hover_info_lbl.setStyleSheet("""
            QLabel {
                font-size: 11px;
                font-weight: 600;
                color: #64748b;
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 4px 10px;
            }
        """)
        hdr_row.addWidget(self._hover_info_lbl)
        layout.addLayout(hdr_row)

        # ── 2. Zero-Activity Notice Banner ──
        self._zero_notice_lbl = QLabel("ℹ️ No financial activity recorded for this period.")
        self._zero_notice_lbl.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 600;
                color: #64748b;
                background-color: #f1f5f9;
                border: 1px dashed #cbd5e1;
                border-radius: 6px;
                padding: 6px 12px;
                margin: 2px 0px;
            }
        """)
        self._zero_notice_lbl.setAlignment(Qt.AlignCenter)
        self._zero_notice_lbl.setVisible(False)
        layout.addWidget(self._zero_notice_lbl)

        # ── 3. QtCharts Chart & View Container ──
        self._chart = QChart()
        self._chart.setBackgroundVisible(False)
        self._chart.setMargins(QMargins(8, 4, 8, 4))
        self._chart.layout().setContentsMargins(0, 0, 0, 0)

        # Legend configuration
        legend = self._chart.legend()
        legend.setVisible(True)
        legend.setAlignment(Qt.AlignTop)
        legend.setFont(QFont("Segoe UI", 9, QFont.Bold))
        legend.setLabelColor(QColor("#475569"))

        self._chart_view = QChartView(self._chart)
        self._chart_view.setRenderHint(QPainter.Antialiasing)
        self._chart_view.setStyleSheet("background: transparent; border: none;")
        self._chart_view.setMinimumHeight(240)

        layout.addWidget(self._chart_view, stretch=1)

    # ── Public Data Binding ──────────────────────────────────────────

    def set_data(self, points: List[DailyFinancialPointDTO]) -> None:
        """
        Bind daily time-series financial data and re-render chart series and axes.
        Accepts pure DailyFinancialPointDTO list without calculating financial values.
        """
        self._daily_points = points or []
        self._hover_info_lbl.setText("Hover over data points to inspect daily totals")

        # 1. Clear previous series and axes
        self._chart.removeAllSeries()
        for axis in self._chart.axes():
            self._chart.removeAxis(axis)

        if not self._daily_points:
            self._zero_notice_lbl.setVisible(True)
            return

        n = len(self._daily_points)

        # 2. Check if all values are zero
        all_zero = all(
            p.net_sales == Decimal("0.00")
            and p.gross_profit == Decimal("0.00")
            and p.opex == Decimal("0.00")
            and p.net_operating_profit == Decimal("0.00")
            for p in self._daily_points
        )
        self._is_all_zero = all_zero
        self._zero_notice_lbl.setVisible(all_zero)

        # 3. Create Series
        series_sales = QLineSeries()
        series_sales.setName("Net Sales")
        pen_sales = QPen(QColor("#2563eb"))
        pen_sales.setWidth(2)
        series_sales.setPen(pen_sales)

        series_gp = QLineSeries()
        series_gp.setName("Gross Profit")
        pen_gp = QPen(QColor("#059669"))
        pen_gp.setWidth(2)
        series_gp.setPen(pen_gp)

        series_opex = QLineSeries()
        series_opex.setName("Store OPEX")
        pen_opex = QPen(QColor("#d97706"))
        pen_opex.setWidth(2)
        pen_opex.setStyle(Qt.DashLine)
        series_opex.setPen(pen_opex)

        series_np = QLineSeries()
        series_np.setName("Net Operating Profit")
        pen_np = QPen(QColor("#7c3aed"))
        pen_np.setWidth(2)
        series_np.setPen(pen_np)

        # Point markers for short ranges (<= 31 days)
        show_markers = n <= 31
        for s in [series_sales, series_gp, series_opex, series_np]:
            s.setPointsVisible(show_markers)
            s.hovered.connect(self._on_series_hovered)

        # 4. Populate Coordinates (Float conversion only at presentation boundary)
        lowest_val = 0.0
        highest_val = 0.0

        for i, p in enumerate(self._daily_points):
            val_sales = float(p.net_sales)
            val_gp = float(p.gross_profit)
            val_opex = float(p.opex)
            val_np = float(p.net_operating_profit)

            series_sales.append(i, val_sales)
            series_gp.append(i, val_gp)
            series_opex.append(i, val_opex)
            series_np.append(i, val_np)

            lowest_val = min(lowest_val, val_sales, val_gp, val_opex, val_np)
            highest_val = max(highest_val, val_sales, val_gp, val_opex, val_np)

        # 5. Y-Axis Bounds & Padding
        if all_zero or (lowest_val == 0.0 and highest_val == 0.0):
            y_min = 0.0
            y_max = 1000.0
        else:
            # Expand bounds with 15% visual headroom/footroom
            if lowest_val < 0.0:
                y_min = lowest_val * 1.15
            else:
                y_min = 0.0

            if highest_val > 0.0:
                y_max = highest_val * 1.15
            else:
                y_max = 1000.0

        axis_y = QValueAxis()
        axis_y.setRange(y_min, y_max)
        axis_y.setLabelFormat("₱%.0f")
        axis_y.setTickCount(6)
        axis_y.setGridLineColor(QColor("#f1f5f9"))
        axis_y.setLinePenColor(QColor("#cbd5e1"))
        axis_y.setLabelsColor(QColor("#64748b"))
        axis_y.setLabelsFont(QFont("Segoe UI", 9))

        # 6. X-Axis with Adaptive Label Density
        axis_x = QCategoryAxis()
        axis_x.setRange(0, max(1, n - 1))
        axis_x.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)
        axis_x.setGridLineColor(QColor("#f1f5f9"))
        axis_x.setLinePenColor(QColor("#cbd5e1"))
        axis_x.setLabelsColor(QColor("#64748b"))
        axis_x.setLabelsFont(QFont("Segoe UI", 9))

        # Calculate label spacing
        if n <= 14:
            step = 1 if n <= 7 else 2
        elif n <= 31:
            step = 4
        elif n <= 90:
            step = 10
        else:
            step = max(1, n // 7)

        selected_indices = set(range(0, n, step))
        selected_indices.add(n - 1)

        for i in sorted(selected_indices):
            p = self._daily_points[i]
            try:
                dt_obj = datetime.strptime(p.date, "%Y-%m-%d")
                label_str = dt_obj.strftime("%b %d")
            except Exception:
                label_str = p.date
            axis_x.append(label_str, i)

        # 7. Add Series to Chart
        self._chart.addSeries(series_sales)
        self._chart.addSeries(series_gp)
        self._chart.addSeries(series_opex)
        self._chart.addSeries(series_np)

        # 8. Render Zero Baseline if Mixed or Negative Data
        if lowest_val < 0.0:
            zero_series = QLineSeries()
            zero_series.setName("Zero Baseline")
            zero_series.append(0, 0.0)
            zero_series.append(max(1, n - 1), 0.0)
            pen_zero = QPen(QColor("#94a3b8"))
            pen_zero.setWidth(1)
            pen_zero.setStyle(Qt.DashLine)
            zero_series.setPen(pen_zero)
            self._chart.addSeries(zero_series)

        # 9. Attach Axes
        self._chart.addAxis(axis_x, Qt.AlignBottom)
        self._chart.addAxis(axis_y, Qt.AlignLeft)

        for s in self._chart.series():
            s.attachAxis(axis_x)
            s.attachAxis(axis_y)

        # Hide Zero Baseline from Legend
        for marker in self._chart.legend().markers():
            if marker.series().name() == "Zero Baseline":
                marker.setVisible(False)
            else:
                marker.clicked.connect(self._on_legend_marker_clicked)

    # ── Interaction & Hover Handling ─────────────────────────────────

    def _on_series_hovered(self, point: QPointF, state: bool) -> None:
        """Display consolidated daily financial metrics in the top header tooltip banner."""
        if not state or not self._daily_points:
            return

        idx = int(round(point.x()))
        if 0 <= idx < len(self._daily_points):
            p = self._daily_points[idx]
            try:
                dt_obj = datetime.strptime(p.date, "%Y-%m-%d")
                date_fmt = dt_obj.strftime("%b %d, %Y")
            except Exception:
                date_fmt = p.date

            if getattr(p, "sales_returns", Decimal("0.00")) > Decimal("0.00"):
                ret_str = f" (Gross: ₱{p.gross_sales:,.2f}, Ret: -₱{p.sales_returns:,.2f})"
            else:
                ret_str = ""

            self._hover_info_lbl.setText(
                f"📅 {date_fmt}  |  "
                f"Net Sales: ₱{p.net_sales:,.2f}{ret_str}  |  "
                f"Gross Profit: ₱{p.gross_profit:,.2f}  |  "
                f"OPEX: ₱{p.opex:,.2f}  |  "
                f"Net Operating Profit: ₱{p.net_operating_profit:,.2f}"
            )

    def _on_legend_marker_clicked(self) -> None:
        """Toggle series visibility when clicking on legend markers."""
        marker = self.sender()
        if isinstance(marker, QLegendMarker):
            series = marker.series()
            if series:
                series.setVisible(not series.isVisible())
                marker.setVisible(True)
                # Dim marker brush opacity when hidden
                color = marker.series().pen().color()
                if not series.isVisible():
                    color.setAlpha(80)
                marker.setLabelBrush(color)

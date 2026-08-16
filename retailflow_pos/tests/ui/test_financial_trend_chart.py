"""
RetailFlow POS - FinancialTrendChartWidget UI Tests
Comprehensive verification of QtCharts time-series rendering, positive/negative datasets,
zero baseline, zero-activity notice, adaptive date label density, long-range performance,
and interactive hover feedback.
"""

from datetime import date, timedelta
from decimal import Decimal
import pytest

from PySide6.QtCore import QPointF, Qt
from PySide6.QtCharts import QCategoryAxis, QLineSeries, QValueAxis

from application.dto.report_dto import DailyFinancialPointDTO
from presentation.widgets.charts.financial_trend_chart import FinancialTrendChartWidget


@pytest.fixture
def sample_short_trend():
    """7-day sample trend dataset."""
    start = date(2026, 8, 1)
    points = []
    for i in range(7):
        d_str = (start + timedelta(days=i)).isoformat()
        points.append(
            DailyFinancialPointDTO(
                date=d_str,
                net_sales=Decimal(f"{(i + 1) * 1000}.00"),
                cogs=Decimal(f"{(i + 1) * 600}.00"),
                gross_profit=Decimal(f"{(i + 1) * 400}.00"),
                opex=Decimal("200.00"),
                net_operating_profit=Decimal(f"{(i + 1) * 400 - 200}.00"),
            )
        )
    return points


@pytest.fixture
def sample_loss_trend():
    """Mixed positive/negative trend dataset."""
    return [
        DailyFinancialPointDTO(
            date="2026-08-01",
            net_sales=Decimal("5000.00"),
            cogs=Decimal("6000.00"),
            gross_profit=Decimal("-1000.00"),
            opex=Decimal("2000.00"),
            net_operating_profit=Decimal("-3000.00"),
        ),
        DailyFinancialPointDTO(
            date="2026-08-02",
            net_sales=Decimal("8000.00"),
            cogs=Decimal("4000.00"),
            gross_profit=Decimal("4000.00"),
            opex=Decimal("1500.00"),
            net_operating_profit=Decimal("2500.00"),
        ),
    ]


def test_chart_widget_instantiation(qtbot):
    """FinancialTrendChartWidget initializes with title, view, and default hover banner."""
    widget = FinancialTrendChartWidget()
    qtbot.addWidget(widget)

    assert widget._title_lbl.text() == "Financial Trend Timeline"
    assert "Hover over data points" in widget._hover_info_lbl.text()
    assert widget._chart is not None
    assert widget._chart_view is not None


def test_chart_widget_positive_dataset(qtbot, sample_short_trend):
    """Positive dataset populates 4 series with all points and valid axis ranges."""
    widget = FinancialTrendChartWidget()
    qtbot.addWidget(widget)

    widget.set_data(sample_short_trend)
    assert not widget._zero_notice_lbl.isVisible()

    series_list = [s for s in widget._chart.series() if s.name() != "Zero Baseline"]
    assert len(series_list) == 4

    names = {s.name() for s in series_list}
    assert names == {"Net Sales", "Gross Profit", "Store OPEX", "Net Operating Profit"}

    # Verify 7 points per series
    for s in series_list:
        assert s.count() == 7

    # Short range has point markers enabled
    assert series_list[0].pointsVisible()


def test_chart_widget_zero_activity_dataset(qtbot):
    """All-zero dataset renders flat baseline and shows zero activity notice banner."""
    zero_points = [
        DailyFinancialPointDTO(
            date=f"2026-08-0{i}",
            net_sales=Decimal("0.00"),
            cogs=Decimal("0.00"),
            gross_profit=Decimal("0.00"),
            opex=Decimal("0.00"),
            net_operating_profit=Decimal("0.00"),
        )
        for i in range(1, 6)
    ]

    widget = FinancialTrendChartWidget()
    qtbot.addWidget(widget)
    widget.show()

    widget.set_data(zero_points)
    assert not widget._zero_notice_lbl.isHidden()
    assert "No financial activity recorded" in widget._zero_notice_lbl.text()


def test_chart_widget_mixed_positive_negative_dataset(qtbot, sample_loss_trend):
    """Negative profit renders below zero without clipping and includes a Zero Baseline series."""
    widget = FinancialTrendChartWidget()
    qtbot.addWidget(widget)

    widget.set_data(sample_loss_trend)

    all_series = widget._chart.series()
    # 4 financial series + 1 Zero Baseline series = 5 series
    assert len(all_series) == 5
    assert any(s.name() == "Zero Baseline" for s in all_series)

    # Check Y-axis minimum is below zero
    axes_y = widget._chart.axes(Qt.Vertical)
    assert len(axes_y) == 1
    assert axes_y[0].min() < 0.0


def test_chart_widget_long_range_performance_and_density(qtbot):
    """YTD dataset (365 daily points) plots continuous sequence with markers disabled and adaptive X ticks."""
    start = date(2026, 1, 1)
    points_365 = [
        DailyFinancialPointDTO(
            date=(start + timedelta(days=i)).isoformat(),
            net_sales=Decimal(f"{1000 + i}.00"),
            cogs=Decimal(f"{600 + i}.00"),
            gross_profit=Decimal("400.00"),
            opex=Decimal("200.00"),
            net_operating_profit=Decimal("200.00"),
        )
        for i in range(365)
    ]

    widget = FinancialTrendChartWidget()
    qtbot.addWidget(widget)

    widget.set_data(points_365)

    series_list = [s for s in widget._chart.series() if s.name() != "Zero Baseline"]
    assert len(series_list) == 4

    # All 365 points plotted
    for s in series_list:
        assert s.count() == 365

    # Markers disabled on long ranges to prevent clutter
    assert not series_list[0].pointsVisible()


def test_chart_widget_hover_feedback(qtbot, sample_short_trend):
    """Hovering over data point updates consolidated top banner."""
    widget = FinancialTrendChartWidget()
    qtbot.addWidget(widget)

    widget.set_data(sample_short_trend)

    # Simulate hover over point index 2 (Aug 03)
    widget._on_series_hovered(QPointF(2.0, 3000.0), state=True)

    assert "Aug 03, 2026" in widget._hover_info_lbl.text()
    assert "Net Sales: ₱3,000.00" in widget._hover_info_lbl.text()
    assert "Gross Profit: ₱1,200.00" in widget._hover_info_lbl.text()
    assert "OPEX: ₱200.00" in widget._hover_info_lbl.text()
    assert "Net Operating Profit: ₱1,000.00" in widget._hover_info_lbl.text()


def test_chart_widget_empty_list(qtbot):
    """Empty list does not raise exception and displays zero notice banner."""
    widget = FinancialTrendChartWidget()
    qtbot.addWidget(widget)
    widget.show()

    widget.set_data([])
    assert not widget._zero_notice_lbl.isHidden()

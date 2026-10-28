"""Interactive charts built from the same filtered campaign rows as the table."""
from PySide6.QtCore import Qt, QMargins
from PySide6.QtGui import QColor, QPainter, QCursor, QPalette
from PySide6.QtCharts import (QBarCategoryAxis, QBarSet, QChart, QChartView,
                             QHorizontalStackedBarSeries, QPieSeries, QValueAxis)
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QToolTip, QVBoxLayout, QWidget

from app.ui_qt.qt_theme import palette


class CampaignCharts(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(10)
        self.delivery_view, self.delivery_note = self.panel(row, "Delivery progress")
        self.quality_view, self.quality_note = self.panel(row, "Lead quality")
        self.setMinimumHeight(260)

    def panel(self, row, title):
        card = QFrame(); card.setObjectName("card"); body = QVBoxLayout(card)
        body.setContentsMargins(10, 8, 10, 6); body.setSpacing(0)
        label = QLabel(title); label.setObjectName("sectionTitle"); body.addWidget(label)
        view = QChartView(); view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumSize(210, 150); view.setFrameShape(QFrame.Shape.NoFrame); body.addWidget(view, 1)
        note = QLabel(); note.setWordWrap(True); note.setObjectName("metricHint"); body.addWidget(note)
        row.addWidget(card, 1)
        return view, note

    def new_chart(self, view):
        settings = self.controller.settings
        dark = settings.appearance_mode == "Dark" or (settings.appearance_mode == "System"
                 and QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128)
        p = palette(settings.color_scheme, dark)
        chart = QChart(); chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart.setBackgroundBrush(QColor(p.surface)); chart.setBackgroundRoundness(0)
        view.setBackgroundBrush(QColor(p.surface))
        chart.layout().setContentsMargins(0, 0, 0, 0)
        chart.setMargins(QMargins(0, 0, 0, 0)); chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        chart.legend().setLabelColor(QColor(p.text)); chart.setTitleBrush(QColor(p.text_muted))
        old = view.chart(); view.setChart(chart)
        if old: old.deleteLater()
        return chart, p

    def refresh(self, rows):
        delivery, p = self.new_chart(self.delivery_view)
        available = [r for r in rows if r.campaign_id and r.allocation is not None and r.delivered is not None]
        visible = sorted(available, key=lambda r: (r.allocation, r.campaign_id), reverse=True)[:8]
        if visible:
            series = QHorizontalStackedBarSeries(); series.setBarWidth(0.65)
            delivered = QBarSet("Delivered"); delivered.setColor(QColor("#0868F9"))
            remaining = QBarSet("Remaining"); remaining.setColor(QColor("#CBDCF6"))
            over = QBarSet("Over allocation"); over.setColor(QColor("#F0B445"))
            for row in visible:
                delivered.append(min(row.delivered, row.allocation)); remaining.append(row.remaining)
                over.append(max(0, row.delivered - row.allocation))
            series.append(delivered); series.append(remaining)
            if any(r.delivered > r.allocation for r in visible): series.append(over)
            else: over.deleteLater()
            delivery.addSeries(series)
            categories = QBarCategoryAxis(); categories.append([r.campaign_id for r in visible])
            categories.setTruncateLabels(False)
            categories.setLabelsColor(QColor(p.text)); categories.setGridLineVisible(False)
            numbers = QValueAxis(); numbers.setLabelFormat("%.0f"); numbers.setLabelsColor(QColor(p.text_muted))
            numbers.setRange(0, max(1, max(max(r.allocation, r.delivered) for r in visible)) * 1.08)
            numbers.setTickCount(4); numbers.setGridLineColor(QColor(p.border))
            delivery.addAxis(categories, Qt.AlignmentFlag.AlignLeft); delivery.addAxis(numbers, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(categories); series.attachAxis(numbers)
            def hover(active, index, _set):
                if active and 0 <= index < len(visible):
                    item = visible[index]
                    QToolTip.showText(QCursor.pos(), f"{item.campaign_name} ({item.campaign_id})\nAllocation: {item.allocation:,}\nDelivered: {item.delivered:,}\nRemaining: {item.remaining:,}")
                else: QToolTip.hideText()
            series.hovered.connect(hover)
            self.delivery_note.setText(f"{len(visible)} of {len(available)} configured campaigns · largest allocations shown · hover for counts")
        else:
            delivery.setTitle("Set allocation and delivered totals to see progress")
            delivery.legend().hide(); self.delivery_note.setText("Delivered totals are entered manually; missing values are excluded.")
        quality, p = self.new_chart(self.quality_view)
        known = [row for row in rows if row.total is not None]
        totals = [sum(getattr(row, key) for row in known) for key in ("qualified", "disqualified", "pending")]
        if sum(totals):
            series = QPieSeries(); series.setHoleSize(0.57)
            for name, color, count in zip(("Qualified", "Disqualified", "Pending / review"), ("#19A67D", "#E36D7B", "#E7BA4B"), totals):
                if not count: continue
                item = series.append(f"{name}: {count:,}", count); item.setColor(QColor(color)); item.setBorderColor(QColor(p.surface))
            quality.addSeries(series)
            series.hovered.connect(lambda item, active: QToolTip.showText(QCursor.pos(), f"{item.label()} ({item.percentage():.1%})") if active else QToolTip.hideText())
            missing = len(rows) - len(known)
            self.quality_note.setText(f"{sum(totals):,} leads in the filtered table · dirty/unvalidated leads remain pending"
                                     + (f" · {missing} unavailable" if missing else ""))
        else:
            quality.setTitle("No lead counts available for this selection")
            quality.legend().hide(); self.quality_note.setText("Counts update from campaign workspaces and the open worksheet.")

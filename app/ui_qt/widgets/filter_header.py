from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QColor, QPolygon
from PySide6.QtWidgets import QHeaderView, QStyleOptionHeader, QStyle


class FilterHeader(QHeaderView):
    filter_requested = Signal(int)
    column_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.filtered_columns = set()
        self.show_column_letters = False
        self.setSectionsClickable(True)
        self.setMinimumSectionSize(65)

    def paintSection(self, painter, rect, logical):
        if not rect.isValid():
            return
        option = QStyleOptionHeader()
        self.initStyleOption(option)
        header_rect=rect.adjusted(0,18,0,0) if self.show_column_letters else rect
        option.rect = header_rect
        option.section = logical
        option.textAlignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        text = str(self.model().headerData(logical, self.orientation(), Qt.ItemDataRole.DisplayRole) or "")
        sorted_column = self.isSortIndicatorShown() and logical == self.sortIndicatorSection()
        option.text = self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(15, rect.width() - (45 if sorted_column else 31)))
        option.sortIndicator = QStyleOptionHeader.SortIndicator.None_
        painter.save()
        if self.show_column_letters:
            number=logical+1; letters=''
            while number:
                number,remainder=divmod(number-1,26); letters=chr(65+remainder)+letters
            letter_rect=QRect(rect.left(),rect.top(),rect.width(),18)
            painter.fillRect(letter_rect,QColor('#edf2ee')); painter.setPen(QColor('#cfdad2'))
            painter.drawRect(letter_rect.adjusted(0,0,-1,-1)); painter.setPen(QColor('#37694a'))
            painter.drawText(letter_rect,Qt.AlignmentFlag.AlignCenter,letters)
        self.style().drawControl(QStyle.ControlElement.CE_Header, option, painter, self)
        button = QRect(rect.right() - 23, header_rect.top() + 3, 21, header_rect.height() - 6)
        active = logical in self.filtered_columns
        painter.setPen(QColor("#0868F9" if active else "#71819B"))
        if active:
            painter.setBrush(QColor("#DFEDFF"))
            painter.drawRoundedRect(button.adjusted(0, 1, -1, -1), 3, 3)
        x, y = button.center().x(), button.center().y()
        painter.setBrush(QColor("#0868F9") if active else Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygon([QPoint(x-5,y-4), QPoint(x+5,y-4), QPoint(x+1,y), QPoint(x+1,y+5), QPoint(x-1,y+4), QPoint(x-1,y)]))
        if self.isSortIndicatorShown() and logical == self.sortIndicatorSection():
            painter.drawText(QRect(rect.right()-39, header_rect.top(), 14, header_rect.height()), Qt.AlignmentFlag.AlignCenter,
                             "↑" if self.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder else "↓")
        painter.restore()

    def mousePressEvent(self, event):
        logical = self.logicalIndexAt(event.position().toPoint())
        if logical >= 0 and event.button() == Qt.MouseButton.LeftButton:
            if self.show_column_letters and event.position().y()<18:
                self.column_selected.emit(logical); event.accept(); return
            right = self.sectionViewportPosition(logical) + self.sectionSize(logical)
            if event.position().x() >= right - 25 and (not self.show_column_letters or event.position().y()>=18):
                self.filter_requested.emit(logical)
                event.accept()
                return
        super().mousePressEvent(event)

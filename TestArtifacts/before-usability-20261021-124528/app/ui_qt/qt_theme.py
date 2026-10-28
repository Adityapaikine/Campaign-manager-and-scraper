from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QtPalette:
    accent: str
    accent_hover: str
    accent_pressed: str
    nav_bg: str
    nav_hover: str
    surface: str
    surface_alt: str
    canvas: str
    border: str
    text: str
    text_muted: str
    success: str = "#217346"
    warning: str = "#C77700"
    danger: str = "#B3261E"


ACCENTS = {
    "Excel Green": ("#217346", "#185C37", "#0F5C36"),
    "Professional Blue": ("#1565C0", "#0D47A1", "#0B3D91"),
    "Teal": ("#087F73", "#06695F", "#05554D"),
    "Purple": ("#6A1B9A", "#4A148C", "#3F0F78"),
    "Orange": ("#EF6C00", "#E65100", "#BF4700"),
    "Slate": ("#455A64", "#37474F", "#263238"),
}


def palette(scheme: str = "Excel Green", dark: bool = False) -> QtPalette:
    accent, hover, pressed = ACCENTS.get(scheme, ACCENTS["Excel Green"])
    if dark:
        return QtPalette(
            accent=accent,
            accent_hover=hover,
            accent_pressed=pressed,
            nav_bg="#111C30",
            nav_hover="#26364D",
            surface="#1A273A",
            surface_alt="#202E43",
            canvas="#101B2B",
            border="#33445D",
            text="#EDF3FC",
            text_muted="#A8B8CF",
        )
    return QtPalette(
        accent=accent,
        accent_hover=hover,
        accent_pressed=pressed,
        nav_bg="#111C30",
        nav_hover="#EDF2F7",
        surface="#FFFFFF",
        surface_alt="#F7F9FC",
        canvas="#F2F5FA",
        border="#DFE6EF",
        text="#16243B",
        text_muted="#65758C",
    )


def build_stylesheet(scheme: str = "Teal", dark: bool = False) -> str:
    p = palette(scheme, dark)
    assets = (Path(__file__).parent / "assets").as_posix()
    return f"""
    QWidget {{ font-family: 'Segoe UI'; font-size: 10pt; color: {p.text}; }}
    QMainWindow, QDialog, QWidget#appRoot, QWidget#scrollContent {{ background: {p.canvas}; }}
    QLabel {{ background: transparent; border: none; }}
    QFrame#topBar {{ background: {p.surface}; border-bottom: 1px solid {p.border}; }}
    QFrame#sideBar {{ background: #111C30; border: none; }}
    QFrame#card, QFrame#toolbarCard, QFrame#metricCard {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px;
    }}
    QFrame#heroCard {{ background: #14263E; border: none; border-radius: 16px; }}
    QLabel#heroTitle {{ color: #F4F8FF; font-size: 25pt; font-weight: 700; }}
    QLabel#heroText {{ color: #BDD0E3; }}
    QLabel#brandMark {{ background: #23B8A2; color: #102A35; border-radius: 10px; font-size: 13pt; font-weight: 800; }}
    QLabel#appTitle {{ color: #F1F6FE; font-size: 13pt; font-weight: 700; }}
    QLabel#brandCaption {{ color: #8FA3BF; font-size: 8pt; }}
    QLabel#navSection {{ color: #8396B3; font-size: 8pt; font-weight: 600; padding: 15px 10px 6px; }}
    QLabel#sidebarNote {{ color: #99ADC7; font-size: 9pt; padding: 12px 6px; }}
    QLabel#pageTitle {{ font-size: 24pt; font-weight: 700; color: {p.text}; }}
    QLabel#sectionTitle {{ font-size: 12pt; font-weight: 650; color: {p.text}; }}
    QLabel#muted {{ color: {p.text_muted}; }}
    QLabel#eyebrow {{ color: {p.accent}; font-size: 8pt; font-weight: 700; padding-bottom: 2px; }}
    QLabel#metricValue {{ font-size: 26pt; font-weight: 700; color: {p.text}; }}
    QLabel#miniMetric {{ font-size: 21pt; font-weight: 700; color: {p.text}; }}
    QLabel#metricHint {{ color: {p.text_muted}; font-size: 9pt; }}
    QLabel#stepNumber {{ color: {p.accent}; background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 8px; font-weight: 700; }}
    QLabel#badge {{ color: {p.text_muted}; background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 12px; padding: 5px 11px; font-size: 9pt; }}
    QLabel#statusPill {{ color: {p.accent}; background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 12px; padding: 5px 10px; font-size: 9pt; }}
    QPushButton, QToolButton {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 8px 12px; font-weight: 500; }}
    QPushButton:hover, QToolButton:hover {{ background: {p.nav_hover}; border-color: #A8B8CB; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {p.border}; }}
    QPushButton:focus, QToolButton:focus {{ border: 1px solid {p.accent}; }}
    QPushButton#primaryButton {{ background: {p.accent}; color: white; border-color: {p.accent}; font-weight: 650; }}
    QPushButton#primaryButton:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
    QPushButton#primaryButton:pressed {{ background: {p.accent_pressed}; }}
    QPushButton#accentButton {{ color: {p.accent}; border-color: {p.accent}; background: {p.surface}; font-weight: 600; }}
    QPushButton#dangerButton {{ background: {p.surface}; color: #C74646; border-color: #E9B7B7; }}
    QPushButton#dangerButton:hover {{ background: #FCE8E8; }}
    QPushButton#ghostButton {{ background: transparent; border: 1px solid transparent; }}
    QPushButton#ghostButton:hover {{ background: {p.nav_hover}; }}
    QPushButton:disabled, QPushButton#primaryButton:disabled, QPushButton#accentButton:disabled, QPushButton#dangerButton:disabled {{ background: {p.surface_alt}; color: {p.text_muted}; border-color: {p.border}; }}
    QPushButton#navButton {{ text-align: left; color: #B5C3D8; padding: 11px 12px; border: none; background: transparent; border-radius: 9px; }}
    QPushButton#navButton:hover {{ color: #F1F6FE; background: #1D2D45; }}
    QPushButton#navButton:checked {{ background: #203C4B; color: #80E3D0; font-weight: 650; border-left: 3px solid #3AC9B1; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 8px;
        selection-background-color: {p.accent}; selection-color: white;
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border-color: {p.accent}; }}
    QLineEdit:read-only {{ background: {p.surface_alt}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {p.text_muted}; background: {p.surface_alt}; }}
    QComboBox {{ padding-right: 26px; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox::down-arrow {{ image: url("{assets}/down.svg"); width: 14px; height: 14px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none; }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{assets}/up.svg"); width: 12px; height: 12px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{assets}/down.svg"); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{ background: {p.surface}; color: {p.text}; selection-background-color: {p.accent}; selection-color: white; padding: 4px; }}
    QPlainTextEdit#activityLog {{ background: {p.surface}; border: none; font-family: 'Consolas'; font-size: 9pt; padding: 14px; }}
    QTabWidget::pane {{ border: none; background: transparent; }}
    QTabBar::tab {{ background: transparent; color: {p.text_muted}; padding: 10px 15px; margin-right: 4px; border-bottom: 2px solid transparent; }}
    QTabBar::tab:hover {{ color: {p.text}; background: {p.surface_alt}; }}
    QTabBar::tab:selected {{ color: {p.accent}; font-weight: 650; border-bottom: 2px solid {p.accent}; }}
    QScrollArea {{ background: transparent; border: none; }}
    QCheckBox {{ spacing: 8px; padding: 3px 0; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #99A8BC; border-radius: 4px; background: {p.surface}; }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border: 2px solid {p.accent}; image: url("{assets}/check.svg"); }}
    QCheckBox:disabled {{ color: {p.text_muted}; }}
    QGroupBox {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; margin-top: 12px; padding-top: 14px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; font-weight: 600; }}
    QTableView, QTableWidget, QListWidget, QTreeWidget {{
        background: {p.surface}; alternate-background-color: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px;
        gridline-color: {p.border}; selection-background-color: {p.accent}; selection-color: white;
    }}
    QHeaderView::section {{ background: {p.surface_alt}; color: {p.text_muted}; border: none; border-right: 1px solid {p.border}; border-bottom: 1px solid {p.border}; padding: 10px 9px; font-size: 9pt; font-weight: 600; }}
    QTableCornerButton::section {{ background: {p.surface_alt}; border: 1px solid {p.border}; }}
    QListWidget::item {{ padding: 12px 10px; border-bottom: 1px solid {p.border}; }}
    QListWidget::item:selected {{ background: {p.accent}; color: white; }}
    QProgressBar {{ border: none; border-radius: 4px; text-align: center; background: {p.border}; color: {p.text_muted}; min-height: 6px; }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0px; }}
    QScrollBar::handle:vertical {{ background: #B6C2D1; min-height: 32px; border-radius: 4px; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0px; }}
    QScrollBar::handle:horizontal {{ background: #B6C2D1; min-width: 32px; border-radius: 4px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QSplitter::handle {{ background: transparent; }}
    QSplitter::handle:hover {{ background: {p.border}; }}
    QMenu {{ background: {p.surface}; border: 1px solid {p.border}; padding: 5px; }}
    QMenu::item {{ padding: 8px 24px 8px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {p.nav_hover}; }}
    QStatusBar {{ background: {p.surface}; border-top: 1px solid {p.border}; padding: 4px 12px; color: {p.text_muted}; }}
    QStatusBar::item {{ border: none; }}
    QDockWidget {{ color: {p.text}; }}
    QToolTip {{ background: #17283F; color: #F1F6FE; border: none; padding: 6px 9px; }}
    """

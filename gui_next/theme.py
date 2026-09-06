# -*- coding: utf-8 -*-
"""Design tokens and QSS for the gui-next research workbench.

Visual language: academic research software × modern IDE × data workbench.
One accent color, flat surfaces, 4/8/12/16/24/32 spacing, 6px radii.
"""

BG = "#F6F7F9"
SURFACE = "#FFFFFF"
TEXT = "#20242A"
MUTED = "#68707D"
BORDER = "#DDE1E7"
PRIMARY = "#315E8A"
SELECTED = "#EAF1F8"
SUCCESS = "#267A57"
WARNING = "#A86916"
ERROR = "#B33A3A"

FONT_FAMILY = '"Segoe UI", "Microsoft YaHei UI"'

# Semantic row accents used by pages (status pills, callouts)
OK = "✓"
PENDING = "○"
WARN = "⚠"


def build_qss() -> str:
    return f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QMainWindow, #Root {{ background: {BG}; }}

/* ---- Sidebar ---- */
#Sidebar {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
}}
#SidebarTitle {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QListWidget#Nav {{
    background: transparent;
    border: none;
    outline: none;
    font-size: 13px;
}}
QListWidget#Nav::item {{
    padding: 8px 12px;
    border-radius: 6px;
    margin: 1px 8px;
    color: {TEXT};
}}
QListWidget#Nav::item:hover {{ background: {BG}; }}
QListWidget#Nav::item:selected {{ background: {SELECTED}; color: {PRIMARY}; font-weight: 600; }}

/* ---- Main surface ---- */
#Page {{
    background: {BG};
}}
#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
#PageTitle {{ font-size: 24px; font-weight: 600; }}
#SectionTitle {{ font-size: 16px; font-weight: 600; }}
#Muted {{ color: {MUTED}; }}
#StatValue {{ font-size: 20px; font-weight: 600; }}
#StatLabel {{ color: {MUTED}; font-size: 11px; }}

#Callout {{
    background: #FBF3E6;
    border: 1px solid {WARNING};
    border-radius: 6px;
}}
#CalloutBlocked {{
    background: #F9ECEC;
    border: 1px solid {ERROR};
    border-radius: 6px;
}}
#CalloutTitle {{ font-weight: 600; }}

/* ---- Tables ---- */
QTableView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: transparent;
    selection-background-color: {SELECTED};
    selection-color: {TEXT};
    alternate-background-color: {SURFACE};
    font-size: 13px;
}}
QTableView::item {{ padding: 4px 6px; border-bottom: 1px solid {BG}; }}
QHeaderView::section {{
    background: {BG};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {BG}; border: none; }}

/* ---- Inputs / buttons ---- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
}}
QLineEdit:focus {{ border-color: {PRIMARY}; }}
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 14px;
}}
QPushButton:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}
QPushButton#Primary {{
    background: {PRIMARY};
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #27507C; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; background: {SURFACE}; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 7px 14px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {PRIMARY}; border-bottom: 2px solid {PRIMARY}; font-weight: 600; }}

QProgressBar {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    height: 14px;
}}
QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 5px; }}

/* ---- Inspector ---- */
#Inspector {{
    background: {SURFACE};
    border-left: 1px solid {BORDER};
}}
#InspectorTitle {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    color: {MUTED};
}}
#InspectorHeading {{ font-size: 15px; font-weight: 600; }}
#InspectorBlock {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QLabel#NodeText {{ background: {SELECTED}; border-radius: 6px; padding: 4px 8px; font-weight: 600; }}

QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QSplitter::handle {{ background: {BG}; }}
"""

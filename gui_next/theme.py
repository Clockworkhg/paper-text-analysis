# -*- coding: utf-8 -*-
"""Design tokens and QSS for the gui-next research workbench.

Visual language: academic research software × modern IDE × data workbench.
One accent color, flat surfaces, 4/8/12/16/24/32 spacing, 6px radii.

Phase 4A: the tokens below are the single source of visual truth. Pages must
not inline colors; semantic glyphs/labels live in gui_next.status.
"""

# ---- palette ---------------------------------------------------------
BG = "#F6F7F9"
SURFACE = "#FFFFFF"
TEXT = "#20242A"
MUTED = "#68707D"
BORDER = "#DDE1E7"
PRIMARY = "#315E8A"
PRIMARY_HOVER = "#27507C"
SELECTED = "#EAF1F8"
SUCCESS = "#267A57"
WARNING = "#A86916"
ERROR = "#B33A3A"

# Derived surfaces (banner tints, from the semantic colors)
WARNING_BG = "#FBF3E6"
ERROR_BG = "#F9ECEC"
INFO_BG = "#EDF2F8"

FONT_FAMILY = '"Segoe UI", "Microsoft YaHei UI"'

# ---- typography scale (px / weight) ----------------------------------
# Page Title 24/600 · Section Title 16/600 · Body 13-14 · Table 13 ·
# Metadata 12 · Caption 11 (uppercase captions only).
T_PAGE_TITLE = ("24px", "600")
T_SECTION_TITLE = ("16px", "600")
T_BODY = ("13px", "400")
T_TABLE = ("13px", "400")
T_METADATA = ("12px", "400")
T_CAPTION = ("11px", "600")

# ---- spacing (the only allowed values) -------------------------------
SP_4, SP_8, SP_12, SP_16, SP_24, SP_32 = 4, 8, 12, 16, 24, 32

# ---- radii / control metrics -----------------------------------------
RADIUS = "6px"
ROW_HEIGHT = 28
HEADER_HEIGHT = 32
INPUT_HEIGHT = 28

# Semantic row glyphs used by pages (status pills, callouts)
OK = "✓"
PENDING = "○"
WARN = "⚠"


def font(size_px: int = 13, weight: int = 400) -> "QFont":  # noqa: F821
    from PySide6.QtGui import QFont
    font_ = QFont()
    font_.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
    font_.setPointSizeF(size_px * 0.75)  # px -> pt at 96 dpi
    font_.setWeight(weight)
    return font_


def build_qss() -> str:
    return f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QMainWindow, #Root {{ background: {BG}; }}

/* ---- Context bar (top) ---- */
#ContextBar {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
#ContextBar QLabel {{ background: transparent; }}
#ContextProject {{ font-size: 13px; font-weight: 600; }}
#ContextChip {{
    color: {MUTED};
    font-size: 12px;
}}
#ContextChipButton {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 2px 10px;
    font-size: 12px;
    color: {TEXT};
}}
#ContextChipButton:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}
#IconOnlyButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px;
    color: {MUTED};
    font-size: 12px;
}}
#IconOnlyButton:hover {{ background: {BG}; color: {TEXT}; border-color: {BORDER}; }}

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
    background: transparent;
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
#NavSection {{
    color: {MUTED};
    font-size: 11px;
    letter-spacing: 1px;
    padding: 8px 20px 2px 20px;
    background: transparent;
}}

/* ---- Main surface ---- */
#Page {{ background: {BG}; }}
#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
#Card > QLabel {{ background: transparent; }}
#PageTitle {{ font-size: 24px; font-weight: 600; }}
#PagePurpose {{ color: {MUTED}; font-size: 13px; }}
#SectionTitle {{ font-size: 16px; font-weight: 600; }}
#Muted {{ color: {MUTED}; }}
#StatValue {{ font-size: 20px; font-weight: 600; }}
#StatLabel {{ color: {MUTED}; font-size: 11px; }}

/* ---- Banners (Info / Warning / Error) ---- */
#Banner {{
    border-radius: 6px;
    padding: 10px 14px;
}}
#Banner > QLabel {{ background: transparent; }}
#BannerTitle {{ font-weight: 600; }}
#Banner[level="info"] {{
    background: {INFO_BG};
    border: 1px solid {PRIMARY};
}}
#Banner[level="warning"] {{
    background: {WARNING_BG};
    border: 1px solid {WARNING};
}}
#Banner[level="error"] {{
    background: {ERROR_BG};
    border: 1px solid {ERROR};
}}
#BannerTitle[level="info"] {{ color: {PRIMARY}; }}
#BannerTitle[level="warning"] {{ color: {WARNING}; }}
#BannerTitle[level="error"] {{ color: {ERROR}; }}

/* ---- Toast ---- */
#Toast {{
    background: {TEXT};
    color: #FFFFFF;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
}}
#Toast QLabel {{ color: #FFFFFF; background: transparent; }}
#Toast QPushButton {{
    background: transparent; color: #FFFFFF; border: none;
    text-decoration: underline; padding: 0 4px;
}}

/* ---- Empty state ---- */
#EmptyState {{ background: transparent; }}
#EmptyTitle {{ font-size: 16px; font-weight: 600; color: {MUTED}; }}
#EmptyHint {{ color: {MUTED}; font-size: 13px; }}

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
QTableView {{ outline: none; }}
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
    min-height: 16px;
}}
QLineEdit:focus {{ border-color: {PRIMARY}; }}
QLineEdit#FilterInput {{
    padding: 5px 8px;
}}
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 14px;
}}
QPushButton:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER}; background: {BG}; }}
QPushButton#Primary {{
    background: {PRIMARY};
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {PRIMARY_HOVER}; }}
QPushButton#Primary:disabled {{ background: {BORDER}; color: {SURFACE}; }}
QPushButton#Flat {{
    background: transparent;
    border: 1px solid transparent;
    color: {PRIMARY};
}}
QPushButton#Flat:hover {{ border-color: {BORDER}; }}

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
    background: transparent;
}}
#InspectorHeading {{ font-size: 15px; font-weight: 600; background: transparent; }}
#InspectorBlock {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
#InspectorBlock > QLabel {{ background: transparent; }}
#InspectorSectionCaption {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#NodeText {{ background: {SELECTED}; border-radius: 6px; padding: 4px 8px; font-weight: 600; }}

/* ---- Command palette ---- */
#Palette {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
#PaletteList {{ background: {SURFACE}; border: none; font-size: 13px; }}
#PaletteList::item {{ padding: 6px 10px; border-radius: 4px; }}
#PaletteList::item:selected {{ background: {SELECTED}; color: {PRIMARY}; }}

QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}
"""

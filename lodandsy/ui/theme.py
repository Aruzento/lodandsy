from string import Template

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtGui import QColor, QFont, QPalette

COLORS = {
    "background": "#191919",
    "surface": "#202020",
    "input": "#232323",
    "border": "#353535",
    "text": "#e5e5e3",
    "muted": "#a6a6a3",
    "focus": "#c9c7bf",
    "primary": "#dededb",
    "primary_hover": "#efefec",
    "primary_pressed": "#bab8b2",
    "hover": "#292929",
    "selection": "#363636",
    "disabled": "#81817f",
    "separator": "#2e2e2e",
    "scrollbar": "#494949",
    "scrollbar_hover": "#676767",
    "warning": "#dec092",
    "error": "#f19a9a",
    "error_surface": "#3c292b",
    "map_tool_checked": "#484848",
}
SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL = 4, 8, 12, 16, 24
ICON_SIZE = 16
ICON_STROKE = 1.35
TOOL_SIZE = 30
TREE_ACTION_SIZE = 24
CONTROL_SIZE = 32
TABLE_ROW = 30
RADIUS = 4


def apply_role(widget, role):
    if widget.property("uiRole") != role:
        widget.setProperty("uiRole", role)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


ADS_STYLE = Template("""
    ads--CDockAreaTitleBar { background: $surface; border-bottom: 1px solid $border; }
    ads--CDockWidgetTab { background: $surface; color: $muted;
                         padding: 4px 8px; border: 0; border-top: 2px solid transparent; }
    ads--CDockWidgetTab QLabel { color: $muted; }
    ads--CDockWidgetTab[activeTab="true"] { background: $hover; border-top-color: $focus; }
    ads--CDockWidgetTab[activeTab="true"] QLabel { color: $text; }
""").substitute(COLORS)

MAP_TOOLBAR_STYLE = Template("""
    QToolBar { spacing:4px; padding:4px; border:0; background:$surface; }
    QToolButton { min-width:36px; max-width:36px; min-height:36px; max-height:36px;
                  padding:0; border:0; border-radius:$radius; }
    QToolButton#mapEditorButton { min-width:156px; max-width:156px; }
    QToolButton:hover { background:$border; }
    QToolButton:focus { border:1px solid $focus; }
    QToolButton:checked { background:$map_tool_checked; }
    QToolBar::separator { background:transparent; width:12px; height:12px; }
    QToolButton::menu-button { width:10px; border:0; }
""").substitute(COLORS, radius=f"{RADIUS}px")

MAP_TOOLBAR_VERTICAL_STYLE = Template("""
    QToolBar::separator { background:$scrollbar; height:1px; margin:5px 7px; }
""").substitute(COLORS)


def apply_theme(app):
    if not app.findChild(QTranslator, "russianQt"):
        translator = QTranslator(app)
        translator.setObjectName("russianQt")
        if translator.load(
            "qtbase_ru", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        ):
            app.installTranslator(translator)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "background",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "input",
        QPalette.ColorRole.AlternateBase: "surface",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "surface",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.Highlight: "selection",
        QPalette.ColorRole.HighlightedText: "text",
        QPalette.ColorRole.ToolTipBase: "surface",
        QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.PlaceholderText: "muted",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(COLORS[color]))
    palette.setColor(QPalette.ColorRole.Link, QColor(COLORS["focus"]))
    for role in [
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ]:
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS["disabled"]))
    app.setPalette(palette)
    app.setStyleSheet(Template("""
        QMenuBar, QMenu, QToolBar, QDockWidget { background:$surface; }
        QToolBar#leftRail, QToolBar#rightRail { border:0; padding:4px; width:38px; }
        QToolBar#leftRail QToolButton, QToolBar#rightRail QToolButton { padding:6px; }
        QScrollBar { background:$surface; border:0; width:10px; height:10px; }
        QScrollBar::handle { background:$scrollbar; min-height:24px; min-width:24px;
                            border-radius:4px; }
        QScrollBar::handle:hover { background:$scrollbar_hover; }
        QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
        QListView { background:$surface; }
        QListView::item { padding:8px; border-bottom:1px solid $hover; }
        QListView::item:hover { background:$hover; }
        QListView::item:selected { background:$selection; }
        QTreeView { background:$surface; }
        QWidget#diceTool { background:$background; }
        QDockWidget#inspectorPanel QLineEdit, QDockWidget#inspectorPanel QComboBox {
            border:0; border-bottom:1px solid $border; background:transparent; padding:5px 0;
        }
        QLineEdit#inspectorTitle { font-size:15px; font-weight:600; }
        QLineEdit#inspectorId { color:$muted; font-size:10px; border:0; background:transparent; }
        QLabel#sectionCaption { color:$muted; font-size:11px; font-weight:600; padding-top:16px; }
        QLabel#pageHeading { font-size:30px; font-weight:600; }
        QLabel#diceTotal { font-size:48px; font-weight:600; color:$text; }
        QWidget#diceResult { background:$surface; border:1px solid $border; border-radius:4px; }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background:$input; }
        QMainWindow::separator { background:$border; width:5px; height:5px; }
        QMainWindow::separator:hover { background:$focus; }
        QWidget#cardPage { background:$background; }
        QLabel#emptyInspector { color:$muted; padding:24px; font-size:14px; }
        QToolButton#portraitImage { background:$background; border:1px solid $border;
                                   padding:0; color:$muted; font-size:16px; }
        QToolButton#portraitImage:hover, QToolButton#portraitImage:focus { border-color:$focus; }
        QLabel#cardTypeBadge { color:$focus; background:$hover;
                              padding:4px 8px; border-radius:3px; }
        QLineEdit#cardHeroTitle { font-size:32px; font-weight:600; padding:4px 0;
                                border:1px solid transparent; background:transparent; }
        QLineEdit#cardHeroTitle:focus { border-bottom:1px solid $focus; }
        QPlainTextEdit#cardSummary { background:transparent; border:0; padding:0;
                                   color:$muted; font-size:14px; }
        QWidget#diceFace { background:$surface; border:1px solid $border; border-radius:6px; }
        QLabel#mapStatus { color:$muted; padding:4px 8px; }
        QHeaderView::section { background:$surface; padding:6px; border:0;
                              border-right:1px solid $border; color:$muted; }
        QTableView { gridline-color:$border; }
        QLabel#mutedCaption { color:$muted; font-size:12px; }
        QLabel#errorNotice { color:$error; padding:4px 12px; }
        QTextEdit#visualCardEditor { background:$background; padding:12px 18px; font-size:15px;
                                    border:2px solid transparent; }
        QTextEdit#visualCardEditor:focus { border-left:2px solid $focus; }
        QGroupBox { border:0; margin-top:14px; font-weight:600; }
        QGroupBox::title { color:$focus; }
        QTabBar::tab { color:$muted; padding:6px 12px; border-bottom:2px solid transparent; }
        QTabBar::tab:selected { color:$text; border-bottom-color:$focus; }
        QTabBar::tab:hover { background:$hover; }
        QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] { border:1px solid $error; }
        QToolBar { border: 0; spacing: 4px; padding: 4px; }
        QDockWidget::title { padding: 7px; color: $focus; }
        QPushButton, QToolButton { padding: 5px 9px; min-height:$control_content;
                                  border: 1px solid $border;
                                  border-radius: $radius; background: $surface; }
        QPushButton:hover, QToolButton:hover { background: $hover; border-color: $muted; }
        QPushButton:pressed, QToolButton:pressed, QToolButton:checked { background: $selection; }
        QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QListView:focus,
        QPlainTextEdit:focus, QTextBrowser:focus, QTreeView:focus, QTableView:focus {
            border: 1px solid $focus;
        }
        QPushButton:disabled, QToolButton:disabled { color: $disabled; background: $surface; }
        QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTreeView, QTableView {
            border: 1px solid $border; border-radius: $radius;
        }
        QLineEdit, QComboBox { padding: 5px; }
        QSpinBox, QDoubleSpinBox { border: 1px solid $border; border-radius: $radius; }
        QTreeView::item { padding: 5px 3px; }
        QTreeView#cardTreeView::item { padding-right: $tree_action_inset; }
        QTreeView::item:hover, QTableView::item:hover { background: $hover; }
        QTreeView::item:selected, QTableView::item:selected { background: $selection; }
        QMenu::item { padding: 6px 22px; }
        QMenu::item:selected, QMenuBar::item:selected { background: $selection; }
        QStatusBar { border-top: 1px solid $border; }
        QSplitter::handle { background: $border; }
        QWidget[uiRole="resultPanel"], QWidget[uiRole="parameterPanel"] {
            background: $surface; border: 1px solid $border; border-radius: $radius;
        }
        QLabel[uiRole="heading"] { font-size: 20px; font-weight: 600; }
        QLabel[uiRole="group"] { color: $muted; font-size: 12px; font-weight: 600; }
        QLabel[uiRole="empty"] { color: $muted; }
        QLabel[uiRole="warning"] { color: $warning; }
        QLabel[uiRole="error"] { color: $error; }
        QLabel[uiRole="total"] { color: $text; font-size: 15px; font-weight: 600; }
        QFrame#abilityTile, QFrame#resourceTile {
            border: 1px solid $border; border-radius: 6px; background: $surface;
        }
        QFrame#abilityTile QLineEdit { padding: 4px; }
        QToolButton#proficiencyToggle { padding: 0; min-height: 24px; min-width: 26px; }
        QToolButton#proficiencyToggle:disabled { color: $text; border: 0; }
        QToolButton#resourceValue:disabled { color: $text; background: transparent; }
        QLabel#proficiencyResult { font-weight: 600; }
        QToolButton#resourceValue { border: 0; text-align: left; }
        QToolButton#sheetDisclosure { border: 0; padding: 6px 0; font-weight: 600; }
        QToolButton#sheetResourceAction { padding: 2px; }
        QComboBox[sheetChoice="true"] QLineEdit {
            padding: 0; border: 0; background: transparent;
        }
        QTreeWidget#settingsNavigation { background: $surface; border: 0; }
        QTreeWidget#settingsNavigation::item { padding: 8px 4px; }
        QCheckBox { spacing: 8px; }
        QCheckBox:focus { background: $hover; }
        QLineEdit[uiRole="compact"] { min-height: 16px; padding: 1px 6px; }
        QToolButton[uiRole="tool"] { padding: 0; min-height: 0; background: transparent; }
        QToolButton[uiRole="tool"]:hover { background: $hover; }
        QToolButton[uiRole="tool"]:checked { background: $selection; border-color: $border; }
        QToolButton#treeRowMenu {
            background: transparent; border: 0; padding: 0; min-height: 0;
            border-radius: $tree_action_radius;
        }
        QToolButton#treeRowMenu:hover { background: $scrollbar; }
        QPushButton[uiRole="primary"], QPushButton#primaryAction {
            background: $primary; border-color: $primary; color: $background; font-weight: 600;
        }
        QPushButton[uiRole="primary"]:hover, QPushButton#primaryAction:hover {
            background: $primary_hover; border-color: $primary_hover;
        }
        QPushButton[uiRole="primary"]:pressed, QPushButton#primaryAction:pressed {
            background: $primary_pressed;
        }
        QPushButton[uiRole="primary"]:focus, QPushButton#primaryAction:focus {
            border: 2px solid $background; padding: 4px 8px;
        }
        QPushButton[uiRole="primary"]:disabled, QPushButton#primaryAction:disabled {
            color: $disabled; background: $surface; border-color: $border;
        }
        QPushButton[uiRole="danger"] { color: $error; }
        QPushButton[uiRole="danger"]:hover { background: $error_surface; }
        QPushButton[uiRole="danger"]:disabled { color: $disabled; }
        QToolTip { background: $surface; color: $text; border: 1px solid $border; padding: 4px; }
    """).substitute(
        COLORS,
        radius=f"{RADIUS}px",
        control_content=f"{CONTROL_SIZE - 12}px",
        tree_action_inset=f"{TREE_ACTION_SIZE + 2 * SPACE_XS}px",
        tree_action_radius=f"{TREE_ACTION_SIZE // 2}px",
    ) + ADS_STYLE)

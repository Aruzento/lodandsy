from PySide6.QtGui import QColor, QFont, QPalette

COLORS = {
    "background": "#191919",
    "surface": "#202020",
    "input": "#202020",
    "border": "#333333",
    "text": "#e5e5e3",
    "muted": "#a6a6a3",
    "accent": "#c9c7bf",
    "selection": "#303030",
    "error": "#f19a9a",
}


def apply_theme(app):
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
    palette.setColor(QPalette.ColorRole.Link, QColor("#c9c7bf"))
    for role in [
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ]:
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#737373"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QMenuBar, QMenu, QToolBar, QDockWidget { background:#202020; }
        QToolBar#leftRail, QToolBar#rightRail { border:0; padding:4px; width:38px; }
        QToolBar#leftRail QToolButton, QToolBar#rightRail QToolButton { padding:6px; }
        QScrollBar { background:#202020; border:0; width:10px; height:10px; }
        QScrollBar::handle { background:#494949; min-height:24px; min-width:24px;
                            border-radius:4px; }
        QScrollBar::handle:hover { background:#676767; }
        QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
        QListView { border:0; background:#202020; outline:0; }
        QListView::item { padding:8px; border-bottom:1px solid #292929; }
        QListView::item:hover { background:#292929; }
        QListView::item:selected { background:#303030; }
        QTreeView { border:0; background:#202020; }
        QWidget#diceTool { background:#191919; }
        QDockWidget#inspectorPanel QLineEdit, QDockWidget#inspectorPanel QComboBox {
            border:0; border-bottom:1px solid #333333; background:transparent; padding:5px 0;
        }
        QLineEdit#inspectorTitle { font-size:15px; font-weight:600; }
        QLineEdit#inspectorId { color:#a6a6a3; font-size:10px; border:0; background:transparent; }
        QLabel#sectionCaption { color:#a6a6a3; font-size:11px; font-weight:600; padding-top:16px; }
        QLabel#pageHeading { font-size:30px; font-weight:600; }
        QLabel#diceTotal { font-size:48px; font-weight:600; color:#e5e5e3; }
        QWidget#diceResult { background:#202020; border:1px solid #333333; border-radius:4px; }
        QLineEdit, QSpinBox, QDoubleSpinBox { background:#202020; }
        QToolButton#portraitImage { padding:0; }
        QMainWindow::separator { background:#333333; width:5px; height:5px; }
        QMainWindow::separator:hover { background:#c9c7bf; }
        QWidget#cardPage { background:#191919; }
        QLabel#emptyInspector { color:#a6a6a3; padding:24px; font-size:14px; }
        QToolButton#portraitImage { background:#191919; border:1px solid #333333;
                                   padding:0; color:#a6a6a3; font-size:16px; }
        QToolButton#portraitImage:hover, QToolButton#portraitImage:focus { border-color:#c9c7bf; }
        QLabel#cardTypeBadge { color:#c9c7bf; background:#292929;
                              padding:4px 8px; border-radius:3px; }
        QLineEdit#cardHeroTitle { font-size:32px; font-weight:600; padding:4px 0;
                                border:1px solid transparent; background:transparent; }
        QLineEdit#cardHeroTitle:focus { border-bottom:1px solid #c9c7bf; }
        QPlainTextEdit#cardSummary { background:transparent; border:0; padding:0;
                                   color:#a6a6a3; font-size:14px; }
        QWidget#diceFace { background:#202020; border:1px solid #333333; border-radius:6px; }
        QPushButton#primaryAction { background:#dededb; color:#191919; font-weight:600; }
        QPushButton#primaryAction:hover { background:#efefec; border-color:#efefec; }
        QLabel#mapStatus { color:#a6a6a3; padding:4px 8px; }
        QHeaderView::section { background:#202020; padding:6px; border:0;
                              border-right:1px solid #333333; color:#a6a6a3; }
        QTableView { gridline-color:#333333; }
        QLabel#mutedCaption { color:#a6a6a3; font-size:12px; }
        QLabel#errorNotice { color:#f19a9a; padding:4px 12px; }
        QTextEdit#visualCardEditor { background:#191919; padding:12px 18px; font-size:15px;
                                    border:2px solid transparent; }
        QTextEdit#visualCardEditor:focus { border-left:2px solid #c9c7bf; }
        QGroupBox { border:0; margin-top:14px; font-weight:600; }
        QGroupBox::title { color:#c9c7bf; }
        QTabBar::tab { color:#a6a6a3; padding:6px 12px; border-bottom:2px solid transparent; }
        QTabBar::tab:selected { color:#e5e5e3; border-bottom-color:#c9c7bf; }
        QTabBar::tab:hover { background:#292929; }
        QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] { border:1px solid #f19a9a; }
        QToolBar { border: 0; spacing: 4px; padding: 4px; }
        QDockWidget::title { padding: 7px; color: #c9c7bf; }
        QPushButton, QToolButton { padding: 5px 9px; min-height:20px;
                                  border: 1px solid transparent;
                                  border-radius: 4px; background: #202020; }
        QPushButton:hover, QToolButton:hover { background: #292929; border-color: #a6a6a3; }
        QPushButton:pressed, QToolButton:pressed, QToolButton:checked { background: #303030; }
        QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus,
        QPlainTextEdit:focus, QTextBrowser:focus, QTreeView:focus, QTableView:focus {
            border: 1px solid #c9c7bf;
        }
        QPushButton:disabled, QToolButton:disabled { color: #737373; background: #202020; }
        QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTreeView, QTableView {
            border: 1px solid #333333; border-radius: 2px;
        }
        QLineEdit, QComboBox { padding: 5px; }
        QTreeView::item { padding: 5px 3px; }
        QTreeView::item:hover, QTableView::item:hover { background: #292929; }
        QTreeView::item:selected, QTableView::item:selected { background: #303030; }
        QMenu::item { padding: 6px 22px; }
        QMenu::item:selected, QMenuBar::item:selected { background: #303030; }
        QStatusBar { border-top: 1px solid #333333; }
        QSplitter::handle { background: #333333; }
        ads--CDockAreaTitleBar { background: #202020; border-bottom: 1px solid #333333; }
        ads--CDockWidgetTab { background: #202020; color: #a6a6a3; padding: 5px; }
        ads--CDockWidgetTab[activeTab="true"] { background: #292929; color: #e5e5e3;
                                             border-top: 2px solid #c9c7bf; }
    """)

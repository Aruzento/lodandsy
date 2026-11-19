from PySide6.QtGui import QColor, QFont, QPalette

COLORS = {
    "background": "#0b111a",
    "surface": "#121c29",
    "input": "#101925",
    "border": "#303e50",
    "text": "#e8edf4",
    "muted": "#aab7ca",
    "gold": "#ceb075",
    "selection": "#304e75",
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
    palette.setColor(QPalette.ColorRole.Link, QColor("#9bc4fa"))
    for role in [
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ]:
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#7e8ca2"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QMainWindow::separator { background:#263447; width:5px; height:5px; }
        QMainWindow::separator:hover { background:#ceb075; }
        QWidget#cardPage { background:#121c29; }
        QLabel#emptyInspector { color:#aab7ca; padding:24px; font-size:14px; }
        QToolButton#portraitImage { background:#0b111a; border:1px solid #263447;
                                   padding:4px; color:#aab7ca; font-size:16px; }
        QToolButton#portraitImage:hover, QToolButton#portraitImage:focus { border-color:#ceb075; }
        QLineEdit#cardHeroTitle { font-size:22px; font-weight:600; padding:4px 0;
                                border:1px solid transparent; background:transparent; }
        QLineEdit#cardHeroTitle:focus { border-bottom:1px solid #ceb075; }
        QPlainTextEdit#cardSummary { background:transparent; border:0; padding:0;
                                   color:#bcc8d8; font-size:14px; }
        QWidget#diceFace { background:#121c29; border:1px solid #263447; border-radius:6px; }
        QPushButton#primaryAction { background:#ceb075; color:#0b111a; font-weight:600; }
        QPushButton#primaryAction:hover { background:#dfc28b; border-color:#dfc28b; }
        QLabel#mapStatus { color:#aab7ca; padding:4px 8px; }
        QHeaderView::section { background:#172235; padding:6px; border:0;
                              border-right:1px solid #263447; color:#bcc8d8; }
        QTableView { gridline-color:#263447; }
        QLabel#mutedCaption { color:#aab7ca; font-size:12px; }
        QLabel#errorNotice { color:#f19a9a; padding:4px 12px; }
        QTextEdit#visualCardEditor { background:#131e2d; padding:12px 18px;
                                    border:2px solid transparent; }
        QTextEdit#visualCardEditor:focus { border-left:2px solid #ceb075; }
        QGroupBox { border:0; margin-top:14px; font-weight:600; }
        QGroupBox::title { color:#ceb075; }
        QTabBar::tab { color:#aab7ca; padding:6px 12px; border-bottom:2px solid transparent; }
        QTabBar::tab:selected { color:#e8edf4; border-bottom-color:#ceb075; }
        QTabBar::tab:hover { background:#263952; }
        QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] { border:1px solid #f19a9a; }
        QToolBar { border: 0; spacing: 4px; padding: 4px; }
        QDockWidget::title { padding: 7px; color: #ceb075; }
        QPushButton, QToolButton { padding: 5px 9px; min-height:20px;
                                  border: 1px solid transparent;
                                  border-radius: 4px; background: #172235; }
        QPushButton:hover, QToolButton:hover { background: #263952; border-color: #7b715c; }
        QPushButton:pressed, QToolButton:pressed, QToolButton:checked { background: #304e75; }
        QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus,
        QPlainTextEdit:focus, QTextBrowser:focus, QTreeView:focus, QTableView:focus {
            border: 1px solid #ceb075;
        }
        QPushButton:disabled, QToolButton:disabled { color: #7e8ca2; background: #131d2b; }
        QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTreeView, QTableView {
            border: 1px solid #38465c; border-radius: 2px;
        }
        QLineEdit, QComboBox { padding: 5px; }
        QTreeView::item { padding: 5px 3px; }
        QTreeView::item:hover, QTableView::item:hover { background: #263952; }
        QTreeView::item:selected, QTableView::item:selected { background: #304e75; }
        QMenu::item { padding: 6px 22px; }
        QMenu::item:selected, QMenuBar::item:selected { background: #304e75; }
        QStatusBar { border-top: 1px solid #38465c; }
        QSplitter::handle { background: #38465c; }
        ads--CDockAreaTitleBar { background: #172235; border-bottom: 1px solid #38465c; }
        ads--CDockWidgetTab { background: #172235; color: #aab7ca; padding: 5px; }
        ads--CDockWidgetTab[activeTab="true"] { background: #263952; color: #e8edf4;
                                             border-top: 2px solid #ceb075; }
    """)

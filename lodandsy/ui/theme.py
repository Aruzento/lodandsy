from PySide6.QtGui import QColor, QFont, QPalette

COLORS = {
    "background": "#0d1421", "surface": "#172235", "input": "#101b2c",
    "border": "#38465c", "text": "#e8edf4", "muted": "#aab7ca",
    "gold": "#ceb075", "selection": "#304e75", "error": "#f19a9a",
}


def apply_theme(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "background", QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "input", QPalette.ColorRole.AlternateBase: "surface",
        QPalette.ColorRole.Text: "text", QPalette.ColorRole.Button: "surface",
        QPalette.ColorRole.ButtonText: "text", QPalette.ColorRole.Highlight: "selection",
        QPalette.ColorRole.HighlightedText: "text", QPalette.ColorRole.ToolTipBase: "surface",
        QPalette.ColorRole.ToolTipText: "text", QPalette.ColorRole.PlaceholderText: "muted",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(COLORS[color]))
    palette.setColor(QPalette.ColorRole.Link, QColor("#9bc4fa"))
    for role in [QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText]:
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#7e8ca2"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QToolBar { border: 0; spacing: 4px; padding: 4px; }
        QDockWidget::title { padding: 7px; color: #ceb075; }
        QPushButton, QToolButton { padding: 5px 9px; border: 1px solid #38465c;
                                  border-radius: 3px; background: #172235; }
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

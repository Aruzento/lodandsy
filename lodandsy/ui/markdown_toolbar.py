from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import QComboBox, QInputDialog, QSpinBox, QToolBar

from lodandsy.application.markdown_commands import format_markdown, markdown_link, utf16_length

VIEW_FONTS = {"sans": "Segoe UI", "serif": "Georgia", "mono": "Consolas"}


class MarkdownToolbar(QToolBar):
    def __init__(self, editor):
        super().__init__(editor)
        self.setMovable(False)
        self.editor = editor
        self.actions_by_name = {}
        self.heading_shortcuts = []
        self.paragraph = QComboBox(self)
        self.paragraph.setAccessibleName("Стиль абзаца Markdown")
        for title, name in [("Обычный", "normal"), ("H1", "h1"), ("H2", "h2"), ("H3", "h3")]:
            self.paragraph.addItem(title, name)
        self.addWidget(self.paragraph)
        self.paragraph.currentIndexChanged.connect(
            lambda: self.apply(self.paragraph.currentData()))
        commands = [
            ("bold", "B", "Жирный", "Ctrl+B"),
            ("italic", "I", "Курсив", "Ctrl+I"),
            ("strike", "S", "Зачёркнутый", "Ctrl+Shift+X"),
            ("quote", ">", "Цитата", "Ctrl+Shift+Q"),
            ("bullet", "•", "Маркированный список", "Ctrl+Shift+8"),
            ("numbered", "1.", "Нумерованный список", "Ctrl+Shift+7"),
            ("inline-code", "`", "Код в строке", "Ctrl+E"),
            ("code-block", "```", "Блок кода", "Ctrl+Shift+E"),
            ("rule", "—", "Разделитель", ""),
        ]
        for name, text, tip, shortcut in commands:
            action = self.command(name, text, tip, shortcut,
                                  lambda _checked=False, n=name: self.apply(n))
            font = QFont()
            font.setBold(name == "bold")
            font.setItalic(name == "italic")
            font.setStrikeOut(name == "strike")
            action.setFont(font)
        self.command("link", "Ссылка", "Вставить ссылку", "Ctrl+K", self.insert_link)
        self.command("image", "Изображение", "Вставить изображение", "",
                     lambda: editor.image_requested.emit(None))
        for level in range(4):
            key = QShortcut(QKeySequence(f"Ctrl+Alt+{level}"), editor)
            key.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            key.activated.connect(lambda n=level: self.apply(f"h{n}" if n else "normal"))
            self.heading_shortcuts.append(key)
        self.addSeparator()
        self.view_preset = QComboBox(self)
        self.view_preset.setAccessibleName("Шрифт просмотра")
        self.view_preset.setToolTip("Шрифт просмотра; Markdown не изменяется")
        for title, key in [("Без засечек", "sans"), ("С засечками", "serif"), ("Моно", "mono")]:
            self.view_preset.addItem(title, key)
        self.addWidget(self.view_preset)
        self.scale = QSpinBox(self)
        self.scale.setRange(75, 200)
        self.scale.setSingleStep(10)
        self.scale.setValue(100)
        self.scale.setSuffix(" %")
        self.scale.setAccessibleName("Масштаб текста")
        self.scale.setToolTip("Масштаб отображения; Markdown не изменяется")
        self.addWidget(self.scale)
        self.view_preset.currentIndexChanged.connect(self.set_fonts)
        self.scale.valueChanged.connect(self.set_fonts)
        editor.text_edit.zoom_requested.connect(self.zoom)
        editor.preview.zoom_requested.connect(self.zoom)
        for shortcut, delta in [("Ctrl++", 10), ("Ctrl+=", 10), ("Ctrl+-", -10)]:
            key = QShortcut(QKeySequence(shortcut), editor)
            key.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            key.activated.connect(lambda d=delta: self.zoom(d))
        editor.text_edit.cursorPositionChanged.connect(self.sync_paragraph)
        editor.mode_combo.currentIndexChanged.connect(self.update_enabled)

    def command(self, name, text, tip, shortcut, callback):
        action = QAction(text, self)
        action.setObjectName(f"markdown-{name}")
        action.setToolTip(tip + (f" ({shortcut})" if shortcut else ""))
        action.setData(action.toolTip())
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(callback)
        self.addAction(action)
        self.editor.addAction(action)
        self.actions_by_name[name] = action
        return action

    def update_enabled(self, *_args):
        enabled = self.editor.card_id is not None and self.editor.mode_combo.currentIndex() != 1
        self.paragraph.setEnabled(enabled)
        self.paragraph.setToolTip(
            "Стиль абзаца" if enabled else "Переключитесь в Источник или Рядом")
        for action in self.actions_by_name.values():
            action.setEnabled(enabled)
            action.setToolTip(action.data() if enabled else "Переключитесь в Источник или Рядом")
        for key in self.heading_shortcuts:
            key.setEnabled(enabled)

    def zoom(self, delta):
        self.scale.setValue(self.scale.value() + delta)

    def sync_paragraph(self):
        line = self.editor.text_edit.textCursor().block().text()
        name = "normal"
        for level in (3, 2, 1):
            if line.startswith("#" * level + " "):
                name = f"h{level}"
                break
        blocker = QSignalBlocker(self.paragraph)
        self.paragraph.setCurrentIndex(self.paragraph.findData(name))
        del blocker

    def apply(self, name):
        if self.editor.card_id is None or self.editor.mode_combo.currentIndex() == 1:
            return
        edit = self.editor.text_edit
        cursor = edit.textCursor()
        change = format_markdown(edit.toPlainText(), cursor.anchor(), cursor.position(), name)
        if change is None:
            return
        vertical, horizontal = edit.verticalScrollBar().value(), edit.horizontalScrollBar().value()
        cursor.setPosition(change.start)
        cursor.setPosition(change.end, QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        cursor.insertText(change.text)
        cursor.endEditBlock()
        cursor.setPosition(change.anchor)
        cursor.setPosition(change.position, QTextCursor.MoveMode.KeepAnchor)
        edit.setTextCursor(cursor)
        edit.setFocus()
        edit.verticalScrollBar().setValue(vertical)
        edit.horizontalScrollBar().setValue(horizontal)
        self.sync_paragraph()

    def insert_link(self):
        edit = self.editor.text_edit
        cursor = edit.textCursor()
        label, accepted = QInputDialog.getText(self.editor, "Ссылка", "Название:",
                                              text=cursor.selectedText() or "Ссылка")
        if not accepted:
            return
        target, accepted = QInputDialog.getText(
            self.editor, "Ссылка", "HTTP/HTTPS, Card или #якорь:")
        if not accepted:
            return
        try:
            text = markdown_link(label, target.strip())
        except ValueError as error:
            self.editor.show_link_error(str(error))
            return
        origin = cursor.selectionStart()
        cursor.beginEditBlock()
        cursor.insertText(text)
        cursor.endEditBlock()
        cursor.setPosition(origin + utf16_length(text))
        edit.setTextCursor(cursor)
        edit.setFocus()

    def set_fonts(self, *_args):
        size = 11 * self.scale.value() / 100
        edit = self.editor.text_edit
        vertical, horizontal = edit.verticalScrollBar().value(), edit.horizontalScrollBar().value()
        source_font = QFont("Consolas")
        source_font.setPointSizeF(size)
        edit.setFont(source_font)
        edit.document().setDefaultFont(source_font)
        self.editor.preview.view_family = VIEW_FONTS[self.view_preset.currentData()]
        self.editor.preview.view_size = size
        self.editor.render_preview()
        edit.verticalScrollBar().setValue(vertical)
        edit.horizontalScrollBar().setValue(horizontal)

    def restore_preferences(self, preset, scale):
        self.view_preset.setCurrentIndex(max(0, self.view_preset.findData(preset)))
        self.scale.setValue(scale)
        self.set_fonts()

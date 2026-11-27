from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeySequence,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QMenu,
    QSpinBox,
    QToolBar,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from lodandsy.application.rich_html import COLORS, FONT_SIZES, FONTS
from lodandsy.ui.icons import icon


class RichToolbar(QToolBar):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor, self.actions_by_name = editor, {}
        self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.paragraph = QComboBox()
        for name in ("Обычный", "Заголовок 1", "Заголовок 2", "Заголовок 3"):
            self.paragraph.addItem(name)
        self.paragraph.setAccessibleName("Стиль абзаца")
        self.paragraph.setMaximumWidth(148)
        self.addWidget(self.paragraph)
        self.paragraph.activated.connect(self.heading)
        self.family = QComboBox()
        for family, key in zip(FONTS, ("sans", "serif", "mono")):
            self.family.addItem(family, key)
        self.family.setAccessibleName("Шрифт текста")
        self.family.activated.connect(lambda i: self.character(fontFamilies=[FONTS[i]]))
        self.size = QComboBox()
        self.size.addItems(list(map(str, FONT_SIZES)))
        self.size.setAccessibleName("Размер текста")
        self.size.activated.connect(lambda i: self.character(fontPointSize=FONT_SIZES[i]))
        self.color = QComboBox()
        for name, value in zip(
            ("Основной", "Золото", "Синий", "Красный", "Зелёный", "Серый", "Чёрный"), COLORS
        ):
            self.color.addItem(name, value)
        self.color.setAccessibleName("Цвет текста")
        self.color.activated.connect(lambda i: self.character(foreground=QColor(COLORS[i])))
        for name, label, tip, key in (
            ("bold", "B", "Жирный", "Ctrl+B"),
            ("italic", "I", "Курсив", "Ctrl+I"),
            ("underline", "U", "Подчёркнутый", "Ctrl+U"),
            ("strike", "S", "Зачёркнутый", "Ctrl+Shift+X"),
            ("bullet", "Маркированный список", "Маркированный список", "Ctrl+Shift+8"),
            ("numbered", "Нумерованный список", "Нумерованный список", "Ctrl+Shift+7"),
            ("quote", "Цитата", "Цитата", "Ctrl+Shift+Q"),
            ("code", "Код", "Блок кода", "Ctrl+E"),
            ("rule", "—", "Разделитель", ""),
            ("link", "Ссылка", "Ссылка", "Ctrl+K"),
            ("image", "Картинка", "Локальное изображение", ""),
            ("open-link", "Перейти", "Открыть ссылку под курсором (или Ctrl+щелчок)", ""),
            ("undo", "↶", "Отменить", "Ctrl+Z"),
            ("redo", "↷", "Повторить", "Ctrl+Y"),
        ):
            action = QAction(label, editor)
            action.setToolTip(tip + (f" · {key}" if key else ""))
            if name in {"undo", "redo", "link", "image"}:
                action.setIcon(icon(name if name != "image" else "map"))
            if name in {"bullet", "numbered"}:
                action.setIcon(icon(name + "_list"))
            if key:
                action.setShortcut(QKeySequence(key))
                action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            if name in {"bold", "italic", "underline", "strike"}:
                action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, n=name: self.apply(n))
            self.actions_by_name[name] = action
            if name in {"bold", "italic", "underline", "link", "image", "undo", "redo"}:
                self.addAction(action)
            editor.text_edit.addAction(action)
        self.alignment = QComboBox()
        self.alignment.addItems(["Слева", "По центру", "Справа", "По ширине"])
        self.alignment.setAccessibleName("Выравнивание абзаца")
        self.alignment.activated.connect(self.align)
        self.scale = QSpinBox()
        self.scale.setRange(75, 200)
        self.scale.setSingleStep(10)
        self.scale.setSuffix("%")
        self.scale.setValue(100)
        self.scale.setAccessibleName("Масштаб просмотра")
        self.scale.valueChanged.connect(editor.set_view_scale)
        editor.text_edit.cursorPositionChanged.connect(self.sync_paragraph)
        editor.text_edit.selectionChanged.connect(self.sync_paragraph)
        editor.text_edit.textChanged.connect(self.sync_paragraph)
        self.format_menu = QMenu(self)
        settings = QWidget()
        form = QFormLayout(settings)
        for label, widget in [
            ("Шрифт", self.family),
            ("Размер", self.size),
            ("Цвет", self.color),
            ("Выравнивание", self.alignment),
            ("Масштаб", self.scale),
        ]:
            form.addRow(label, widget)
        setting_action = QWidgetAction(self.format_menu)
        setting_action.setDefaultWidget(settings)
        self.format_menu.addAction(setting_action)
        self.format_menu.addSeparator()
        for name in ("strike", "bullet", "numbered", "quote", "code", "rule", "open-link"):
            self.format_menu.addAction(self.actions_by_name[name])
        more = QToolButton()
        more.setText("Формат")
        more.setToolTip("Шрифт, цвет, списки и дополнительные команды")
        more.setMenu(self.format_menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.addWidget(more)

    def character(self, **values):
        if self.editor.text_edit.isReadOnly():
            return
        format = QTextCharFormat()
        for name, value in values.items():
            getattr(format, "set" + name[0].upper() + name[1:])(value)
        self.editor.text_edit.mergeCurrentCharFormat(format)
        self.editor.text_edit.setFocus()

    def heading(self, level):
        edit = self.editor.text_edit
        if edit.isReadOnly():
            return
        selection = edit.textCursor()
        block = edit.document().findBlock(selection.selectionStart())
        end = selection.selectionEnd()
        style = QTextCharFormat()
        style.setFontPointSize((11, 28, 22, 16)[level])
        style.setFontWeight(QFont.Weight.Bold if level else QFont.Weight.Normal)
        style.setProperty(QTextFormat.Property.FontSizeAdjustment, 0)
        selection.beginEditBlock()
        while block.isValid():
            cursor = QTextCursor(block)
            block_format = cursor.blockFormat()
            block_format.setHeadingLevel(level)
            cursor.setBlockFormat(block_format)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            if cursor.hasSelection():
                cursor.mergeCharFormat(style)
            else:
                cursor.mergeBlockCharFormat(style)
            block = block.next()
            if not block.isValid() or block.position() >= end:
                break
        selection.endEditBlock()
        edit.setTextCursor(selection)
        edit.setFocus()
        self.sync_paragraph()

    def align(self, index):
        self.editor.text_edit.setAlignment(
            (
                Qt.AlignmentFlag.AlignLeft,
                Qt.AlignmentFlag.AlignHCenter,
                Qt.AlignmentFlag.AlignRight,
                Qt.AlignmentFlag.AlignJustify,
            )[index]
        )
        self.editor.text_edit.setFocus()

    def apply(self, name):
        edit = self.editor.text_edit
        if name == "open-link":
            self.editor.open_current_link()
            return
        if edit.isReadOnly():
            return
        if name in {"undo", "redo"}:
            getattr(edit, name)()
        elif name in {"bold", "italic", "underline", "strike"}:
            f = edit.currentCharFormat()
            values = {
                "bold": (
                    "fontWeight",
                    QFont.Weight.Normal if f.font().bold() else QFont.Weight.Bold,
                ),
                "italic": ("fontItalic", not f.fontItalic()),
                "underline": ("fontUnderline", not f.fontUnderline()),
                "strike": ("fontStrikeOut", not f.fontStrikeOut()),
            }
            key, value = values[name]
            self.character(**{key: value})
        elif name == "link":
            self.editor.request_link()
        elif name == "image":
            self.editor.image_requested.emit(None)
        else:
            cursor = edit.textCursor()
            cursor.beginEditBlock()
            if name in {"bullet", "numbered"}:
                style = (
                    QTextListFormat.Style.ListDisc
                    if name == "bullet"
                    else QTextListFormat.Style.ListDecimal
                )
                current = cursor.currentList()
                if current and current.format().style() == style:
                    start, end = cursor.selectionStart(), cursor.selectionEnd()
                    block = cursor.document().findBlock(start)
                    while block.isValid() and block.position() <= end:
                        if block.textList():
                            block.textList().remove(block)
                        block = block.next()
                else:
                    format = QTextListFormat()
                    format.setStyle(style)
                    cursor.createList(format)
            elif name in {"quote", "code"}:
                format = QTextBlockFormat()
                format.setIndent(0 if cursor.blockFormat().indent() else 1)
                format.setNonBreakableLines(name == "code")
                cursor.mergeBlockFormat(format)
                if name == "code":
                    char = QTextCharFormat()
                    char.setFontFamilies(["Consolas"])
                    cursor.mergeCharFormat(char)
            elif name == "rule":
                cursor.insertHtml("<hr>")
            cursor.endEditBlock()
            edit.setTextCursor(cursor)
        edit.setFocus()
        self.sync_paragraph()

    def sync_paragraph(self):
        edit = self.editor.text_edit
        if not hasattr(self, "alignment"):
            return
        f = edit.currentCharFormat()
        controls = [self.paragraph, self.family, self.size, self.color, self.alignment]
        blockers = [QSignalBlocker(control) for control in controls]
        self.paragraph.setCurrentIndex(min(3, edit.textCursor().blockFormat().headingLevel()))
        families = f.fontFamilies() or ["Segoe UI"]
        self.family.setCurrentText(families[0])
        self.size.setCurrentText(str(round(f.fontPointSize() or 11)))
        color = f.foreground().color().name()
        if color in COLORS:
            self.color.setCurrentIndex(COLORS.index(color))
        flags = (
            Qt.AlignmentFlag.AlignLeft,
            Qt.AlignmentFlag.AlignHCenter,
            Qt.AlignmentFlag.AlignRight,
            Qt.AlignmentFlag.AlignJustify,
        )
        self.alignment.setCurrentIndex(
            next((i for i, flag in enumerate(flags) if edit.alignment() & flag), 0)
        )
        for name, checked in (
            ("bold", f.font().bold()),
            ("italic", f.fontItalic()),
            ("underline", f.fontUnderline()),
            ("strike", f.fontStrikeOut()),
        ):
            self.actions_by_name[name].setChecked(checked)
        writable = edit.isEnabled() and not edit.isReadOnly()
        for control in controls:
            control.setEnabled(writable)
        for name, action in self.actions_by_name.items():
            action.setEnabled(writable if name != "open-link" else True)
        self.actions_by_name["undo"].setEnabled(writable and edit.document().isUndoAvailable())
        self.actions_by_name["redo"].setEnabled(writable and edit.document().isRedoAvailable())
        del blockers

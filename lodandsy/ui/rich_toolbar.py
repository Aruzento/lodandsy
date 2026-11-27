from PySide6.QtCore import QSignalBlocker, QSize, Qt
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
    QHBoxLayout,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.rich_html import COLORS, FONT_SIZES, FONTS
from lodandsy.ui.icons import icon
from lodandsy.ui.theme import ICON_SIZE, SPACE_XS, TOOL_SIZE, apply_role

ALIGNMENTS = (
    ("align-left", Qt.AlignmentFlag.AlignLeft),
    ("align-center", Qt.AlignmentFlag.AlignHCenter),
    ("align-right", Qt.AlignmentFlag.AlignRight),
    ("align-justify", Qt.AlignmentFlag.AlignJustify),
)
CHARACTER_SIZE_PROPERTIES = (
    QTextFormat.Property.FontPixelSize, QTextFormat.Property.FontSizeAdjustment,
)
HIGHLIGHTS = (None, "#67493b", "#635627", "#314e5d", "#354f39", "#633d4c")


def selected_blocks(cursor):
    block = cursor.document().findBlock(cursor.selectionStart())
    while block.isValid():
        yield block
        block = block.next()
        if block.position() >= cursor.selectionEnd():
            return


def selected_runs(cursor):
    start, end = cursor.selectionStart(), cursor.selectionEnd()
    runs = []
    for block in selected_blocks(cursor):
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            iterator += 1
            begin = fragment.position()
            low, high = max(start, begin), min(end, begin + fragment.length())
            style = fragment.charFormat()
            if low < high and not style.isImageFormat():
                runs.append((low, high, style))
    return runs


def set_run(cursor, start, end, style):
    part = QTextCursor(cursor.document())
    part.setPosition(start)
    part.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    part.setCharFormat(style)


class RichToolbar(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor, self.actions_by_name = editor, {}
        self.setObjectName("richToolbar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(SPACE_XS)
        self._arrangement = ()
        self.paragraph = QComboBox()
        for name in ("Обычный", "Заголовок 1", "Заголовок 2", "Заголовок 3"):
            self.paragraph.addItem(name)
        self.paragraph.setAccessibleName("Стиль абзаца")
        self.paragraph.setFixedWidth(142)
        self.paragraph.activated.connect(self.heading)
        self.family = QComboBox()
        for family, key in zip(FONTS, ("sans", "serif", "mono")):
            self.family.addItem(family, key)
        self.family.setAccessibleName("Шрифт текста")
        self.family.setFixedWidth(114)
        self.family.textActivated.connect(lambda value: self.character(fontFamilies=[value]))
        self.size = QComboBox()
        self.size.addItems(list(map(str, FONT_SIZES)))
        self.size.setAccessibleName("Размер текста")
        self.size.setFixedWidth(52)
        self.size.textActivated.connect(lambda value: self.character(fontPointSize=float(value)))
        self.color = self._palette("Цвет текста", "foreground", COLORS)
        self.highlight = self._palette("Выделение текста", "background", HIGHLIGHTS)
        buttons = {}
        for name, tip, svg, key in (
            ("bold", "Жирный", "format_bold", "Ctrl+B"),
            ("italic", "Курсив", "format_italic", "Ctrl+I"),
            ("underline", "Подчёркнутый", "format_underline", "Ctrl+U"),
            ("strike", "Зачёркнутый", "format_strike", "Ctrl+Shift+X"),
            ("bullet", "Маркированный список", "bullet_list", "Ctrl+Shift+8"),
            ("numbered", "Нумерованный список", "numbered_list", "Ctrl+Shift+7"),
            ("indent-less", "Уменьшить отступ", "indent_less", ""),
            ("indent-more", "Увеличить отступ", "indent_more", ""),
            ("align-left", "По левому краю", "align_left", ""),
            ("align-center", "По центру", "align_center", ""),
            ("align-right", "По правому краю", "align_right", ""),
            ("align-justify", "По ширине", "align_justify", ""),
            ("quote", "Цитата", "format_quote", "Ctrl+Shift+Q"),
            ("code", "Блок кода", "format_code", "Ctrl+E"),
            ("rule", "Разделитель", "format_rule", ""),
            ("link", "Вставить или изменить ссылку", "link", "Ctrl+K"),
            ("image", "Локальное изображение", "map", ""),
            ("open-link", "Открыть ссылку под курсором", "open_link", ""),
            ("clear", "Очистить форматирование", "format_clear", ""),
            ("undo", "Отменить", "undo", "Ctrl+Z"),
            ("redo", "Повторить", "redo", "Ctrl+Y"),
        ):
            action = QAction(icon(svg), tip, editor)
            action.setToolTip(tip + (f" · {key}" if key else ""))
            if key:
                action.setShortcut(QKeySequence(key))
                action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            if name in {"bold", "italic", "underline", "strike", "bullet", "numbered"} or (
                name.startswith("align-")
            ):
                action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, n=name: self.apply(n))
            self.actions_by_name[name] = action
            editor.text_edit.addAction(action)
            button = QToolButton()
            button.setDefaultAction(action)
            button.setAccessibleName(tip)
            button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            button.setFixedSize(TOOL_SIZE, TOOL_SIZE)
            apply_role(button, "tool")
            buttons[name] = button
        self.scale = QSpinBox()
        self.scale.setRange(75, 200)
        self.scale.setSingleStep(10)
        self.scale.setSuffix("%")
        self.scale.setValue(100)
        self.scale.setAccessibleName("Масштаб просмотра")
        self.scale.setToolTip("Масштаб просмотра")
        self.scale.setFixedWidth(73)
        self.scale.valueChanged.connect(editor.set_view_scale)
        editor.text_edit.cursorPositionChanged.connect(self.sync_paragraph)
        editor.text_edit.selectionChanged.connect(self.sync_paragraph)
        editor.text_edit.textChanged.connect(self.sync_paragraph)
        self.groups = []
        for items in (
            ("undo", "redo"), (self.paragraph,), (self.family, self.size),
            ("bold", "italic", "underline", "strike", "clear"), (self.color, self.highlight),
            ("bullet", "numbered", "indent-less", "indent-more"),
            ("align-left", "align-center", "align-right", "align-justify"),
            ("link", "open-link", "image", "quote", "code", "rule"), (self.scale,),
        ):
            group = QWidget(self)
            group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            layout = QHBoxLayout(group)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)
            for item in items:
                layout.addWidget(buttons[item] if isinstance(item, str) else item)
            self.groups.append(group)
        self._wrap(640)

    def _palette(self, label, property_name, colors):
        selector = QComboBox()
        selector.setAccessibleName(label)
        selector.setToolTip(label)
        selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        selector.setFixedWidth(108)
        for value in colors:
            glyph = "format_color" if property_name == "foreground" else "format_highlight"
            label = "Без цвета" if value is None else value
            selector.addItem(icon(glyph, tint=value), label, value)
        selector.activated.connect(
            lambda i: self.character(**{
                property_name: QColor(selector.itemData(i) or Qt.GlobalColor.transparent)
            })
        )
        return selector

    def minimumSizeHint(self):
        return QSize(max((g.minimumSizeHint().width() for g in self.groups), default=0), 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._wrap(event.size().width())

    def _wrap(self, width):
        arrangement = [[]]
        occupied = 0
        for group in self.groups:
            required = group.minimumSizeHint().width()
            if occupied and occupied + required > width:
                arrangement.append([])
                occupied = 0
            arrangement[-1].append(group)
            occupied += required + SPACE_XS
        if arrangement == self._arrangement:
            return
        self._arrangement = arrangement
        while self.rows.count():
            row = self.rows.takeAt(0).layout()
            while row.count():
                row.takeAt(0)
            row.deleteLater()
        for groups in arrangement:
            row = QHBoxLayout()
            row.setSpacing(SPACE_XS)
            for group in groups:
                row.addWidget(group)
            row.addStretch()
            self.rows.addLayout(row)
        self.updateGeometry()

    def character(self, **values):
        if self.editor.text_edit.isReadOnly():
            return
        format = QTextCharFormat()
        for name, value in values.items():
            getattr(format, "set" + name[0].upper() + name[1:])(value)
        edit = self.editor.text_edit
        properties = []
        if "fontPointSize" in values:
            properties.extend(CHARACTER_SIZE_PROPERTIES)
        if "fontFamilies" in values:
            properties.extend((QTextFormat.Property.FontFamily, QTextFormat.Property.FontStyleName))
        cursor = edit.textCursor()
        if properties and cursor.hasSelection():
            cursor.beginEditBlock()
            self._overwrite_font(cursor, format, properties)
            cursor.endEditBlock()
            edit.setTextCursor(cursor)
        elif properties:
            style = edit.currentCharFormat()
            for prop in properties:
                style.clearProperty(prop)
            style.merge(format)
            edit.setCurrentCharFormat(style)
        else:
            edit.mergeCurrentCharFormat(format)
        edit.setFocus()
        self.sync_paragraph()

    @staticmethod
    def _overwrite_font(cursor, format, properties):
        for start, end, style in selected_runs(cursor):
            for prop in properties:
                style.clearProperty(prop)
            style.merge(format)
            set_run(cursor, start, end, style)

    def heading(self, level):
        edit = self.editor.text_edit
        if edit.isReadOnly():
            return
        selection = edit.textCursor()
        style = QTextCharFormat()
        style.setFontPointSize((11, 28, 22, 16)[level])
        style.setFontWeight(QFont.Weight.Bold if level else QFont.Weight.Normal)
        style.setProperty(QTextFormat.Property.FontSizeAdjustment, 0)
        selection.beginEditBlock()
        for block in selected_blocks(selection):
            cursor = QTextCursor(block)
            block_format = cursor.blockFormat()
            block_format.setHeadingLevel(level)
            cursor.setBlockFormat(block_format)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            if cursor.hasSelection():
                self._overwrite_font(cursor, style, CHARACTER_SIZE_PROPERTIES)
            else:
                cursor.mergeBlockCharFormat(style)
        selection.endEditBlock()
        edit.setTextCursor(selection)
        edit.setFocus()
        self.sync_paragraph()

    def align(self, index):
        edit = self.editor.text_edit
        if edit.isReadOnly():
            return
        cursor = edit.textCursor()
        cursor.beginEditBlock()
        for block in selected_blocks(cursor):
            individual = QTextCursor(block)
            current = individual.blockFormat()
            current.setAlignment(ALIGNMENTS[index][1])
            individual.setBlockFormat(current)
        cursor.endEditBlock()
        edit.setFocus()
        self.sync_paragraph()

    def clear_formatting(self):
        edit = self.editor.text_edit
        cursor = edit.textCursor()
        if not cursor.hasSelection():
            edit.setCurrentCharFormat(QTextCharFormat())
            return
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.beginEditBlock()
        for low, high, original in selected_runs(cursor):
            clean = QTextCharFormat()
            if original.isAnchor():
                clean.setAnchor(True)
                clean.setAnchorHref(original.anchorHref())
                clean.setAnchorNames(original.anchorNames())
                clean.setFontUnderline(True)
            set_run(cursor, low, high, clean)
        for block in selected_blocks(cursor):
            if start <= block.position() and end >= block.position() + block.length() - 1:
                part = QTextCursor(block)
                format = QTextBlockFormat()
                if block.textList() is not None:
                    format.setObjectIndex(block.blockFormat().objectIndex())
                part.setBlockFormat(format)
                part.setBlockCharFormat(QTextCharFormat())
        cursor.endEditBlock()
        edit.setTextCursor(cursor)

    def apply(self, name):
        edit = self.editor.text_edit
        if name == "open-link":
            self.editor.open_current_link()
            return
        if edit.isReadOnly():
            return
        if name in {"undo", "redo"}:
            getattr(edit, name)()
        elif name == "clear":
            self.clear_formatting()
        elif name.startswith("align-"):
            self.align(next(index for index, (key, _) in enumerate(ALIGNMENTS) if key == name))
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
                    for block in selected_blocks(cursor):
                        if block.textList():
                            block.textList().remove(block)
                else:
                    format = current.format() if current else QTextListFormat()
                    format.setStyle(style)
                    self._paragraph_selection(cursor).createList(format)
            elif name in {"indent-less", "indent-more"}:
                delta = 1 if name == "indent-more" else -1
                current = cursor.currentList()
                if current:
                    format = current.format()
                    format.setIndent(max(1, min(32, format.indent() + delta)))
                    self._paragraph_selection(cursor).createList(format)
                else:
                    for block in selected_blocks(cursor):
                        selection = QTextCursor(block)
                        format = selection.blockFormat()
                        format.setIndent(max(0, min(32, format.indent() + delta)))
                        selection.setBlockFormat(format)
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

    @staticmethod
    def _paragraph_selection(cursor):
        first, *rest = selected_blocks(cursor)
        last = rest[-1] if rest else first
        selection = QTextCursor(first)
        selection.setPosition(last.position() + last.length() - 1, QTextCursor.MoveMode.KeepAnchor)
        return selection

    @staticmethod
    def _select_text(control, text, presets):
        if control.count() > presets:
            control.removeItem(presets)
        if control.findText(text) < 0:
            control.addItem(text)
        control.setCurrentText(text)
        control.setToolTip(control.accessibleName() + " · " + text)

    @staticmethod
    def _select_color(control, value, presets, glyph):
        if control.count() > len(presets):
            control.removeItem(len(presets))
        if value is None:
            control.setCurrentIndex(0)
            return
        index = control.findData(value)
        if index < 0:
            control.addItem(icon(glyph, tint=value), value, value)
            index = control.count() - 1
        control.setCurrentIndex(index)

    def sync_paragraph(self):
        edit = self.editor.text_edit
        f = edit.currentCharFormat()
        controls = [self.paragraph, self.family, self.size, self.color, self.highlight]
        blockers = [QSignalBlocker(control) for control in controls]
        self.paragraph.setCurrentIndex(min(3, edit.textCursor().blockFormat().headingLevel()))
        families = f.fontFamilies() or ["Segoe UI"]
        self._select_text(self.family, families[0], len(FONTS))
        pixels = f.font().pixelSize()
        size = f.fontPointSize() or (pixels * 72 / 96 if pixels > 0 else 11)
        self._select_text(self.size, f"{size:g}", len(FONT_SIZES))
        color = (f.foreground().color().name()
                 if f.hasProperty(QTextFormat.Property.ForegroundBrush) else COLORS[0])
        self._select_color(self.color, color, COLORS, "format_color")
        background = (f.background().color()
                      if f.hasProperty(QTextFormat.Property.BackgroundBrush) else None)
        highlight = background.name() if background and background.alpha() else None
        self._select_color(self.highlight, highlight, HIGHLIGHTS, "format_highlight")
        for name, flag in ALIGNMENTS:
            self.actions_by_name[name].setChecked(bool(edit.alignment() & flag))
        active_list = edit.textCursor().currentList()
        for name, style in (("bullet", QTextListFormat.Style.ListDisc),
                            ("numbered", QTextListFormat.Style.ListDecimal)):
            checked = bool(active_list and active_list.format().style() == style)
            self.actions_by_name[name].setChecked(checked)
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

from html import escape
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QTextCursor, QTextFormat, QTextImageFormat
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QTabBar,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.rich_html import allowed_link, sanitize_html
from lodandsy.application.rich_text_codec import serialize_document
from lodandsy.domain.card import EMPTY_DOCUMENT
from lodandsy.domain.card_schema import CARD_TYPES, parse_field
from lodandsy.ui.icons import icon
from lodandsy.ui.portrait_panel import PortraitPanel
from lodandsy.ui.rich_document import RichDocument
from lodandsy.ui.rich_toolbar import RichToolbar


class RichTextEdit(QTextEdit):
    image_requested = Signal(object)
    link_activated = Signal(QUrl)
    notice = Signal(str)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if self.isReadOnly():
            return
        if source.hasImage():
            self.image_requested.emit(source.imageData())
        elif source.hasUrls():
            urls = source.urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                self.image_requested.emit(Path(urls[0].toLocalFile()))
        elif source.hasHtml():
            try:
                html, warnings = sanitize_html(source.html())
                self.textCursor().insertHtml(html)
                if warnings:
                    self.notice.emit("Некоторые объекты вставки заблокированы: " + warnings[0])
            except ValueError as error:
                self.notice.emit(str(error))
        elif source.hasText():
            if len(source.text().encode("utf-8")) > 2**20:
                self.notice.emit("Текст вставки превышает 1 MiB")
            else:
                self.textCursor().insertText(source.text())

    def mouseReleaseEvent(self, event):
        target = self.anchorAt(event.position().toPoint())
        if (
            event.button() == Qt.MouseButton.LeftButton
            and target
            and (self.isReadOnly() or event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            self.link_activated.emit(QUrl(target))
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class CardEditorWidget(QWidget):
    image_requested = Signal(object)
    content_changed = Signal(str, str)
    link_activated = Signal(QUrl)
    links_changed = Signal()
    copy_link_requested = Signal(str)
    fields_edited = Signal(object)
    options_edited = Signal(object)
    draft_changed = Signal(str, object)
    discard_drafts_requested = Signal()
    section_action_requested = Signal(str, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardPage")
        self._card_id, self._content, self._model = None, None, None
        self.current_section = None
        self.document_state = None
        self.configure_document = lambda document: None
        self.table_factory = lambda key: None
        self.entity_options = lambda: ()
        self.text_edit = RichTextEdit(self)
        self.text_edit.setObjectName("visualCardEditor")
        self.text_edit.setMinimumSize(80, 120)
        self.text_edit.setDocument(RichDocument(EMPTY_DOCUMENT, self.text_edit))
        self.text_edit.setPlaceholderText("Начните писать…")
        self.text_edit.image_requested.connect(self.image_requested)
        self.text_edit.link_activated.connect(self.link_activated)
        self.text_edit.notice.connect(self.show_link_error)
        self.text_edit.textChanged.connect(self._changed)
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("cardHeroTitle")
        self.title_edit.setAccessibleName("Название карточки")
        self.title_edit.setMaxLength(2000)
        self.title_edit.textEdited.connect(lambda text: self._edit_field("title", text))
        self.type_combo = QComboBox()
        self.type_combo.setAccessibleName("Тип карточки")
        for definition in CARD_TYPES.values():
            self.type_combo.addItem(definition.title, definition.id)
        self.type_combo.currentIndexChanged.connect(
            lambda _: (
                self.options_edited.emit({"card_type": self.type_combo.currentData()})
                if self.card_id
                else None
            )
        )
        self.copy_link_button = QToolButton()
        self.copy_link_button.setIcon(icon("link"))
        self.copy_link_button.setToolTip("Копировать ссылку на карточку")
        self.copy_link_button.clicked.connect(lambda: self.copy_link_requested.emit(self.card_id))
        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setObjectName("cardSummary")
        self.summary_edit.setPlaceholderText("Краткое описание")
        self.summary_edit.setAccessibleName("Краткое описание")
        self.summary_edit.setFixedHeight(70)
        self.summary_edit.textChanged.connect(
            lambda: self._edit_field("summary", self.summary_edit.toPlainText())
        )
        self.metadata = QWidget()
        meta = QVBoxLayout(self.metadata)
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(12)
        row = QHBoxLayout()
        row.addWidget(self.title_edit, 1)
        row.addWidget(self.copy_link_button)
        meta.addLayout(row)
        meta.addWidget(self.type_combo, 0, Qt.AlignmentFlag.AlignLeft)
        meta.addWidget(self.summary_edit)
        meta.addStretch()
        self.portrait_panel = PortraitPanel(self)
        self.hero = QWidget()
        self.hero_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.hero)
        self.hero_layout.setContentsMargins(0, 0, 0, 0)
        self.hero_layout.setSpacing(24)
        self.hero_layout.addWidget(self.metadata, 1)
        self.hero_layout.addWidget(self.portrait_panel)
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 20, 24, 16)
        header_layout.addWidget(self.hero)
        self.header_scroll = QScrollArea()
        self.header_scroll.setWidgetResizable(True)
        self.header_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.header_scroll.setWidget(header)
        self.header_scroll.setMaximumHeight(360)
        self.header_scroll.setMinimumHeight(140)
        self.header_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.section_bar = QTabBar()
        self.section_bar.setExpanding(False)
        self.section_bar.setUsesScrollButtons(True)
        self.section_bar.currentChanged.connect(self._section_changed)
        self.section_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.section_bar.customContextMenuRequested.connect(self._section_menu)
        self.section_add = QToolButton()
        self.section_add.setIcon(icon("plus"))
        self.section_add.setToolTip("Добавить вкладку")
        self.section_add.clicked.connect(self._add_section_menu)
        tabs = QHBoxLayout()
        tabs.setContentsMargins(16, 0, 16, 0)
        tabs.addWidget(self.section_bar, 1)
        tabs.addWidget(self.section_add)
        self.format_toolbar = RichToolbar(self)
        from PySide6.QtWidgets import QStackedWidget

        self.body = QStackedWidget()
        rich = QWidget()
        rich_layout = QVBoxLayout(rich)
        rich_layout.setContentsMargins(20, 4, 20, 12)
        rich_layout.setSpacing(4)
        rich_layout.addWidget(self.format_toolbar)
        rich_layout.addWidget(self.text_edit, 1)
        self.body.addWidget(rich)
        self.table_page = QWidget()
        self.table_layout = QVBoxLayout(self.table_page)
        self.table_layout.setContentsMargins(16, 8, 16, 16)
        self.body.addWidget(self.table_page)
        self._embedded_tables = {}
        self.link_status = QLabel()
        self.link_status.setWordWrap(True)
        self.link_status.setTextFormat(Qt.TextFormat.PlainText)
        self.link_status.setObjectName("errorNotice")
        self.link_status.hide()
        self.validation_status = QLabel()
        self.validation_status.setTextFormat(Qt.TextFormat.PlainText)
        self.validation_status.setObjectName("errorNotice")
        self.validation_status.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header_scroll)
        layout.addLayout(tabs)
        layout.addWidget(self.body, 1)
        layout.addWidget(self.validation_status)
        layout.addWidget(self.link_status)

    def _edit_field(self, key, text):
        if self.card_id is None:
            return
        try:
            value = parse_field(key, text)
            self.fields_edited.emit({key: value})
        except ValueError:
            self.draft_changed.emit(key, text)

    def set_canonical(self, card, drafts=None):
        self._model, self._card_id = card, card.id
        drafts = drafts or {}
        for widget, key, value in [
            (self.title_edit, "title", card.title),
            (self.summary_edit, "summary", card.value("summary") or ""),
        ]:
            value = drafts.get((card.id, key), value)
            blocker = QSignalBlocker(widget)
            if isinstance(widget, QPlainTextEdit):
                if widget.toPlainText() != value:
                    widget.setPlainText(value)
            elif widget.text() != value:
                widget.setText(value)
            del blocker
        blocker = QSignalBlocker(self.type_combo)
        self.type_combo.setCurrentIndex(self.type_combo.findData(card.card_type))
        del blocker
        self.portrait_panel.set_portrait(card.portrait)
        keys = [s.id for s in card.sections]
        current = [self.section_bar.tabData(i) for i in range(self.section_bar.count())]
        blocker = QSignalBlocker(self.section_bar)
        if current != keys:
            while self.section_bar.count():
                self.section_bar.removeTab(0)
            for section in card.sections:
                i = self.section_bar.addTab(section.title)
                self.section_bar.setTabData(i, section.id)
        else:
            for i, section in enumerate(card.sections):
                self.section_bar.setTabText(i, section.title)
        del blocker
        if self.document_state:
            blocker = QSignalBlocker(self.text_edit)
            for section in card.sections:
                if section.kind == "rich_text":
                    state = self.document_state.existing(section.id)
                    if state and (card.id, section.id) not in drafts:
                        state.sync_content(section.content)
            del blocker
        key = self.current_section if self.current_section in keys else (keys[0] if keys else None)
        if key:
            self.select_section(key, capture=False)
        else:
            self.body.setCurrentIndex(0)
            self.text_edit.setEnabled(False)
        invalid = [key for (identity, key) in drafts if identity == card.id]
        self.validation_status.setText(
            "Несохранённый ошибочный ввод · исправьте или отмените" if invalid else ""
        )
        self.validation_status.setVisible(bool(invalid))

    def _section_changed(self, index):
        if index >= 0:
            self.select_section(self.section_bar.tabData(index))

    def select_section(self, key, capture=True):
        if not self._model:
            return
        try:
            section = self._model.section(key)
        except ValueError:
            return
        if capture and self.document_state and self.current_section:
            previous = self.document_state.existing(self.current_section)
            if previous and self.body.currentIndex() == 0:
                previous.capture_position(self)
        self.current_section = key
        if self.document_state:
            self.document_state.active_section = key
        if section.kind == "rich_text":
            self.body.setCurrentIndex(0)
            self.text_edit.setEnabled(True)
            if self.document_state:
                state = self.document_state.section(key, section.content)
                self.configure_document(state.document)
                if self.text_edit.document() is not state.document:
                    self.set_document(self.card_id, state.document)
                    state.restore_position(self)
            else:
                self.set_card(self.card_id, section.content)
        else:
            self.body.setCurrentIndex(1)
            self._show_table(section)
        blocker = QSignalBlocker(self.section_bar)
        for i in range(self.section_bar.count()):
            if self.section_bar.tabData(i) == key:
                self.section_bar.setCurrentIndex(i)
                break
        del blocker

    def _show_table(self, section):
        while self.table_layout.count():
            item = self.table_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                if item.widget() not in self._embedded_tables.values():
                    item.widget().deleteLater()
        previous = self._embedded_tables.get(section.id)
        widget = self.table_factory(section, previous)
        if previous is not None and previous is not widget:
            previous.deleteLater()
            self._embedded_tables.pop(section.id, None)
        if widget:
            self._embedded_tables[section.id] = widget
            self.table_layout.addWidget(widget)
            widget.show()
        else:
            from PySide6.QtWidgets import QPushButton

            if section.table_id:
                notice = QLabel("Связанная таблица удалена или больше не является дочерней")
                notice.setWordWrap(True)
                self.table_layout.addWidget(notice)
            button = QPushButton(
                "Заменить ссылку…"
                if section.table_id
                else "Создать инвентарь"
                if section.purpose == "inventory"
                else "Создать дочернюю таблицу"
            )
            button.clicked.connect(
                lambda: self.section_action_requested.emit(
                    "link_table" if section.table_id else "table", section.id, None
                )
            )
            self.table_layout.addWidget(button)
        self.table_layout.addStretch()

    def _add_section_menu(self):
        menu = QMenu(self)
        menu.addAction(
            "Текстовая вкладка…", lambda: self.section_action_requested.emit("add_text", "", None)
        )
        menu.addAction(
            "Дочерняя таблица…", lambda: self.section_action_requested.emit("add_table", "", None)
        )
        menu.exec(self.section_add.mapToGlobal(self.section_add.rect().bottomLeft()))

    def _section_menu(self, point):
        i = self.section_bar.tabAt(point)
        if i < 0:
            return
        key = self.section_bar.tabData(i)
        menu = QMenu(self)
        for title, action in [
            ("Переименовать…", "rename"),
            ("Переместить влево", "left"),
            ("Переместить вправо", "right"),
            ("Удалить вкладку…", "delete"),
        ]:
            menu.addAction(title, lambda a=action: self.section_action_requested.emit(a, key, None))
        menu.exec(self.section_bar.mapToGlobal(point))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < 640
        desired = QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        self.hero_layout.setDirection(desired)
        self.portrait_panel.setMaximumWidth(220 if narrow else 280)

    @property
    def card_id(self):
        return self._card_id

    def set_document(self, card_id, document):
        blocker = QSignalBlocker(self.text_edit)
        self._card_id = card_id
        self.text_edit.setDocument(document)
        self._content = document.canonical_content
        del blocker
        self.format_toolbar.sync_paragraph()
        self.refresh_links()

    def set_card(self, card_id, content):
        if self.card_id == card_id and content == self._content:
            return
        document = self.text_edit.document()
        if (
            document.pending_content == content
            or document.canonical_content == content
            and document.pending_content is None
        ):
            self._card_id, self._content = card_id, content
            document.canonical_content = content
            document.pending_content = None
            return
        # External updates preserve the session document and use one native Undo command.
        blocker = QSignalBlocker(self.text_edit)
        cursor = QTextCursor(self.text_edit.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        cursor.insertHtml(content)
        cursor.endEditBlock()
        self._card_id, self._content = card_id, content
        self.text_edit.document().canonical_content = content
        del blocker

    def _changed(self):
        if self.card_id is None:
            return
        try:
            content = serialize_document(self.text_edit.document())
        except ValueError as error:
            blocker = QSignalBlocker(self.text_edit)
            self.text_edit.undo()
            del blocker
            self.show_link_error(str(error))
            return
        if content != self._content or self.text_edit.document().pending_content is not None:
            self.text_edit.document().pending_content = content
            self.content_changed.emit(self.card_id, content)
            self.links_changed.emit()

    def clear_card(self):
        self._card_id = None
        blocker = QSignalBlocker(self.text_edit)
        self.text_edit.clear()
        del blocker
        self.text_edit.setEnabled(False)

    def refresh_links(self):
        self.links_changed.emit()

    def set_view_scale(self, scale):
        document = self.text_edit.document()
        if hasattr(document, "set_view_scale"):
            document.set_view_scale(scale, self.text_edit.logicalDpiY())
            self.text_edit.viewport().update()

    def show_link_error(self, message):
        self.link_status.setText(message)
        self.link_status.setVisible(bool(message))

    def open_current_link(self):
        href = self.text_edit.textCursor().charFormat().anchorHref()
        if href:
            self.link_activated.emit(QUrl(href))

    def request_link(self):
        options = tuple(self.entity_options())
        labels = [
            "Внешняя HTTP/HTTPS-ссылка…",
            *[f"{e.title} · {e.kind} · {e.id}" for e in options],
        ]
        choice, ok = QInputDialog.getItem(self, "Вставить ссылку", "Документ:", labels, 0, False)
        if not ok:
            return
        cursor = self.text_edit.textCursor()
        label = cursor.selectedText()
        if choice == labels[0]:
            href, ok = QInputDialog.getText(self, "Внешняя ссылка", "HTTP/HTTPS URL:")
            if not ok:
                return
            if not href.startswith(("https://", "http://")) or not allowed_link(href):
                self.show_link_error("Разрешены только корректные HTTP/HTTPS-ссылки")
                return
            label = label or href
        else:
            entity = options[labels.index(choice) - 1]
            href, label = f"lodandsy://entity/{entity.id}", label or entity.title
        cursor.insertHtml(f'<a href="{escape(href, quote=True)}">{escape(label)}</a>')

    def insert_asset(self, cursor, path, alt):
        format = QTextImageFormat()
        format.setName(path)
        format.setWidth(400)
        format.setProperty(QTextFormat.Property.ImageAltText, alt)
        cursor.insertImage(format)

    def contextMenuEvent(self, event):
        menu = self.text_edit.createStandardContextMenu()
        if self.text_edit.textCursor().charFormat().anchorHref():
            action = QAction("Открыть ссылку", menu)
            action.triggered.connect(self.open_current_link)
            menu.addAction(action)
        menu.exec(event.globalPos())
        menu.deleteLater()

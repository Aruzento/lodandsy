from html import escape
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QTextCursor, QTextFormat, QTextImageFormat
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QFrame,
    QGroupBox,
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
from lodandsy.domain.card_schema import CARD_TYPES, FIELD_DEFINITIONS, parse_field
from lodandsy.domain.card_templates import CARD_TEMPLATES, card_template
from lodandsy.ui.card_fields import CardFieldsForm, field_text
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardPage")
        self._card_id, self._content = None, None
        self._model = None
        self.current_section = "description"
        self.document_state = None
        self.configure_document = lambda document: None
        self.entity_options = lambda: ()
        self.text_edit = RichTextEdit(self)
        self.text_edit.setObjectName("visualCardEditor")
        self.text_edit.setMinimumWidth(80)
        self.text_edit.setMinimumHeight(120)
        self.text_edit.setDocument(RichDocument(EMPTY_DOCUMENT, self.text_edit))
        self.text_edit.setPlaceholderText("Описание, заметки, история…")
        self.text_edit.image_requested.connect(self.image_requested)
        self.text_edit.link_activated.connect(self.link_activated)
        self.text_edit.notice.connect(self.show_link_error)
        self.text_edit.textChanged.connect(self._changed)
        self.copy_link_button = QToolButton()
        self.copy_link_button.setIcon(icon("link"))
        self.copy_link_button.setToolTip("Копировать ссылку на карточку")
        self.copy_link_button.clicked.connect(lambda: self.copy_link_requested.emit(self.card_id))
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("cardHeroTitle")
        self.title_edit.setAccessibleName("Название карточки")
        self.title_edit.setMaxLength(2000)
        self.title_edit.textEdited.connect(lambda text: self._edit_field("title", text))
        self.type_combo = QComboBox()
        self.type_combo.setAccessibleName("Тип карточки")
        self.template_combo = QComboBox()
        self.template_combo.setAccessibleName("Компоновка карточки")
        for definition in CARD_TYPES.values():
            self.type_combo.addItem(definition.title, definition.id)
        for template in CARD_TEMPLATES:
            self.template_combo.addItem(template.title, template.id)
        self.type_combo.currentIndexChanged.connect(
            lambda _: self._option("card_type", self.type_combo)
        )
        self.template_combo.currentIndexChanged.connect(
            lambda _: self._option("template_id", self.template_combo)
        )
        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setObjectName("cardSummary")
        self.summary_edit.setPlaceholderText("Краткое описание")
        self.summary_edit.setFixedHeight(64)
        self.summary_edit.setAccessibleName("Краткое описание")
        self.summary_edit.textChanged.connect(
            lambda: self._edit_field("summary", self.summary_edit.toPlainText())
        )
        self.tags_edit = QLineEdit()
        self.aliases_edit = QLineEdit()
        for widget, key, label in [
            (self.tags_edit, "tags", "Теги через запятую"),
            (self.aliases_edit, "aliases", "Также известен как"),
        ]:
            widget.setPlaceholderText(label)
            widget.setAccessibleName(label)
            widget.textEdited.connect(lambda text, k=key: self._edit_field(k, text))
        self.metadata = QWidget()
        meta = QVBoxLayout(self.metadata)
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(self.title_edit, 1)
        row.addWidget(self.copy_link_button)
        more = QToolButton()
        more.setText("…")
        more.setToolTip("Действия карточки")
        menu = QMenu(more)
        menu.addAction("Добавить поле…", self.add_field)
        menu.addAction("Выбрать портрет…", lambda: self.portrait_panel.image_requested.emit())
        menu.addAction("Отменить ошибочный ввод", self.discard_drafts_requested.emit)
        sections = menu.addMenu("Разделы")
        for key, definition in FIELD_DEFINITIONS.items():
            if definition.data_type == "richtext":
                sections.addAction(definition.label, lambda k=key: self.select_section(k))
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(more)
        meta.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.type_combo)
        row.addWidget(self.template_combo)
        row.addStretch()
        meta.addLayout(row)
        meta.addWidget(self.summary_edit)
        meta.addWidget(self.tags_edit)
        meta.addWidget(self.aliases_edit)
        self.portrait_panel = PortraitPanel(self)
        self.hero = QWidget()
        self.hero_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.hero)
        self.hero_layout.setContentsMargins(0, 0, 0, 0)
        self.hero_layout.setSpacing(20)
        self.hero_layout.addWidget(self.metadata, 3)
        self.hero_layout.addWidget(self.portrait_panel, 1)
        self.details = QGroupBox("Характеристики")
        self.details.setCheckable(True)
        self.details.setChecked(True)
        detail_layout = QVBoxLayout(self.details)
        self.fields_form = CardFieldsForm()
        detail_layout.addWidget(self.fields_form)
        self.details.toggled.connect(self.fields_form.setVisible)
        self.fields_form.edited.connect(self.fields_edited)
        self.fields_form.draft_changed.connect(self.draft_changed)
        self.details.hide()
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 8)
        header_layout.setSpacing(16)
        header_layout.addWidget(self.hero)
        header_layout.addWidget(self.details)
        self.header_scroll = QScrollArea()
        self.header_scroll.setWidgetResizable(True)
        self.header_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.header_scroll.setWidget(header)
        self.header_scroll.setMaximumHeight(340)
        self.header_scroll.setMinimumHeight(120)
        self.header_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.section_bar = QTabBar()
        self.section_bar.setExpanding(False)
        self.section_bar.setUsesScrollButtons(True)
        self.section_bar.currentChanged.connect(self._section_changed)
        self.format_toolbar = RichToolbar(self)
        self.link_status = QLabel()
        self.link_status.setTextFormat(Qt.TextFormat.PlainText)
        self.link_status.setWordWrap(True)
        self.link_status.setObjectName("errorNotice")
        self.link_status.hide()
        self.validation_status = QLabel()
        self.validation_status.setTextFormat(Qt.TextFormat.PlainText)
        self.validation_status.setObjectName("errorNotice")
        self.validation_status.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.header_scroll)
        layout.addWidget(self.section_bar)
        layout.addWidget(self.format_toolbar)
        layout.addWidget(self.text_edit, 1)
        layout.addWidget(self.validation_status)
        layout.addWidget(self.link_status)

    def _option(self, key, combo):
        if self.card_id is not None and combo.currentData():
            self.options_edited.emit({key: combo.currentData()})

    def _edit_field(self, key, text):
        if self.card_id is None:
            return
        try:
            value = parse_field(key, text)
            self.draft_changed.emit(key, None)
            self.fields_edited.emit({key: value})
        except ValueError:
            self.draft_changed.emit(key, text)

    def add_field(self):
        labels = [
            f.label
            for f in FIELD_DEFINITIONS.values()
            if f.group not in {"source"} and f.key not in {"title", "description", "portrait"}
        ]
        keys = [
            f.key
            for f in FIELD_DEFINITIONS.values()
            if f.group not in {"source"} and f.key not in {"title", "description", "portrait"}
        ]
        label, ok = QInputDialog.getItem(
            self, "Поле карточки", "Встроенное поле:", labels, 0, False
        )
        if ok:
            key = keys[labels.index(label)]
            self.fields_edited.emit({key: FIELD_DEFINITIONS[key].default})

    def set_canonical(self, card, drafts=None):
        initial = self._model is None
        self._model = card
        self._card_id = card.id
        drafts = drafts or {}
        for widget, key, value in [
            (self.title_edit, "title", card.title),
            (self.summary_edit, "summary", card.value("summary") or ""),
            (self.tags_edit, "tags", field_text(card.value("tags"))),
            (self.aliases_edit, "aliases", field_text(card.value("aliases"))),
        ]:
            value = drafts.get((card.id, key), value)
            blocker = QSignalBlocker(widget)
            if isinstance(widget, QPlainTextEdit):
                if widget.toPlainText() != value:
                    widget.setPlainText(value)
            elif widget.text() != value:
                widget.setText(value)
            widget.setProperty("invalid", (card.id, key) in drafts)
            del blocker
        for combo, value in [
            (self.type_combo, card.card_type),
            (self.template_combo, card.template_id),
        ]:
            blocker = QSignalBlocker(combo)
            combo.setCurrentIndex(combo.findData(value))
            del blocker
        self.portrait_panel.set_portrait(card.portrait)
        self.portrait_panel.setVisible(
            card.portrait is not None or card.card_type in {"character", "creature"}
        )
        keys = CARD_TYPES[card.card_type].fields
        self.fields_form.set_card(card, keys, drafts)
        template = card_template(card.template_id)
        self.details.setVisible(
            bool(keys)
            and ("details" in template.sections or any(k in dict(card.values) for k in keys))
        )
        section = (
            self.document_state.active_section
            if initial and self.document_state
            else self.current_section
        )
        keys = [k for k in template.sections if k != "details"]
        keys += [k for k, v in card.values if FIELD_DEFINITIONS[k].data_type == "richtext" and v]
        keys = list(dict.fromkeys([*keys, section]))
        blocker = QSignalBlocker(self.section_bar)
        while self.section_bar.count():
            self.section_bar.removeTab(0)
        for key in keys:
            index = self.section_bar.addTab(FIELD_DEFINITIONS[key].label)
            self.section_bar.setTabData(index, key)
        del blocker
        if self.document_state:
            text_blocker = QSignalBlocker(self.text_edit)
            for key, state in [
                ("description", self.document_state),
                *self.document_state.sections.items(),
            ]:
                state.sync_content(card.value(key) or EMPTY_DOCUMENT)
            del text_blocker
            self.select_section(section, capture=not initial)
        else:
            self.set_card(card.id, card.content)
        invalid = [key for (identity, key) in drafts if identity == card.id]
        self.validation_status.setText(
            "Исправьте поле: " + ", ".join(FIELD_DEFINITIONS[k].label for k in invalid)
        )
        self.validation_status.setVisible(bool(invalid))

    def _section_changed(self, index):
        if index >= 0:
            self.select_section(self.section_bar.tabData(index))

    def select_section(self, key, capture=True):
        if (
            not self.document_state
            or not self._model
            or key not in FIELD_DEFINITIONS
            or FIELD_DEFINITIONS[key].data_type != "richtext"
        ):
            return
        root = self.document_state
        if capture:
            root.section(self.current_section).capture_position(self)
        state = root.section(key, self._model.value(key) or EMPTY_DOCUMENT)
        self.current_section = key
        root.active_section = key
        self.configure_document(state.document)
        self.set_document(self.card_id, state.document)
        state.restore_position(self)
        index = next(
            (i for i in range(self.section_bar.count()) if self.section_bar.tabData(i) == key), -1
        )
        blocker = QSignalBlocker(self.section_bar)
        if index < 0:
            index = self.section_bar.addTab(FIELD_DEFINITIONS[key].label)
            self.section_bar.setTabData(index, key)
        self.section_bar.setCurrentIndex(index)
        del blocker

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < 640
        desired = QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        if self.hero_layout.direction() != desired:
            self.hero_layout.removeWidget(self.metadata)
            self.hero_layout.removeWidget(self.portrait_panel)
            self.hero_layout.setDirection(desired)
            if narrow:
                self.hero_layout.addWidget(self.portrait_panel)
                self.hero_layout.addWidget(self.metadata)
            else:
                self.hero_layout.addWidget(self.metadata, 3)
                self.hero_layout.addWidget(self.portrait_panel, 1)

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
        if content != self._content:
            self._content = content
            self.text_edit.document().canonical_content = content
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

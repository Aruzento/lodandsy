# ADR-029 — Qt-компоновка и жизнь ресурсов раздела

Утверждён пакет6-rev3. В соответствующих частях заменяет ADR-024–026 и navy/gold
макет итерации5. Стек, rich Qt HTML, libvips и текущий SQLite writer сохраняются.

## Решение

Шапка Card — одна native layout: breadcrumb/copy link, затем квадратный портрет слева,
type/title/summary справа. Отдельный header QScrollArea удалён. Размер портрета задаётся
одной политикой редактора:184 logical px обычно,132 на узкой странице,88 при сильном
сжатии. Нет resize→fixedHeight→iconSize feedback loop: PortraitImage рисует непосредственно
в актуальный contentsRect. Summary имеет полный редактор в диалоге с тем же field buffer.
Prose ограничена760px, Table занимает доступную ширину. Inspector сгруппирован по
характеристикам/организации, UUID доступен через компактное меню.

Нейтральная палитра применяется к QPalette/QSS/ADS/rails/scrollbar/menus/focus/иконкам,
Segoe UI и title32px/body15px. Изображения и пользовательское форматирование не
обесцвечиваются. Map Editor: вертикальная tool rail, центр canvas, справа единая панель
слоёв/Object Card library/properties; Viewer остаётся отдельным. Undo/Redo используют
QToolButton IconOnly с динамическим command tooltip и WidgetWithChildrenShortcut.
Dice: ограниченная ширина, сетка7кубиков+modifier, formula/action, result/copy/repeat/history.

Crop хранится в oriented source coordinates. Для квадратной рамки base scale равен
frameSide/min(W,H); обратный zoom=min(W,H)/sourceCropSide. Уже сохранённый rect, в том
числе прямоугольный, отображается aspect-fit и возвращается без изменений до явного
drag/zoom/reset. Это устраняет повторное неявное кадрирование при изменении аспекта.
Card и наследующий token используют один rect; общий asset остаётся неизменным.

Библиотека карты — модель публичного EntityQueries, только Card(object) с доступным
main image. Поиск title/aliases, UUID/path в tooltip, сохранение выбора по UUID.
Импорт создаёт и выбирает Object Card в одной общей транзакции. Размещение фиксирует
исходный asset и oriented aspect с long edge128, игнорирует portrait crop. Последующие
изменения/удаление Card не меняют размещённый raster. Front layer показывается первым;
up повышает domain position и scene z, крайние команды выключены.

Удаление раздела адресно отменяет его pending rich publication, освобождает QTextDocument,
preferences и embedded view; живые разделы сохраняют native Undo. Закрытый editor хранит
только живые session documents. Асинхронный image import захватывает section UUID и
session document, не widget; после удаления раздела результат не публикуется. Generation
защищает смену проекта. Не принятый/ошибочный asset callback откатывает resource registry
совместно с Entity transaction. CardCollection.create без content однозначно принимает
explicit sections; явные конфликтующие content+sections по-прежнему отклоняются.

## Доказательства и границы

C targeted:30passed4.07s. D targeted:25passed/1skip и устаревшее ожидание немедленной
rich publication, переведённое на semantic flush; итоговый gate фиксируется в отчёте6.
Проверены10 no-change crop циклов для landscape/portrait/square и DPR1/1.5/2, оригинал,
общая token projection, две Map surfaces, layer order/Undo, Object library и neutral palette.
Lifecycle:100 rich/table create/open/delete циклов, Qt destroyed/weak refs, pending image,
удаление primary/закрытого раздела/relink; сохраняется Undo живого QTextDocument.

Официальные референсы изучены как принципы, без заимствования runtime/графики:
[LegendKeeper](https://www.legendkeeper.com/legendkeeper-101-the-basics-beyond/),
[0.12](https://www.legendkeeper.com/changelog/legendkeeper-0-12-0-0/),
[Notion relations](https://www.notion.com/help/relations-and-rollups),
[style](https://www.notion.com/help/customize-and-style-your-content),
[Foundry tiles](https://foundryvtt.com/article/tiles/), [Dungeondraft](https://dungeondraft.net/).
Приватные макеты/портрет6 находятся только в ignored .prototype-deps и не публикуются.

Full snapshot writer и synchronous backup≤4GiB не переписаны. Измерения —
docs/validation/iteration6-*.json, physical DPI/Windows capture учитываются отдельно.
Пересмотр: подтверждённая проблема композиции при конкретном размере/DPI либо измеренное
нарушение resource/lifecycle bounds; не замена Qt Widgets или второй store.

Итог6: полный pytest394passed/1skip64.76s, после финальных local fixes targeted29passed3.66s (включая новый constraint regression) и22passed2.52s portrait/layout. Ruff/pip/diff clean. Actual imports83modules/174edges/0cycles; draw.io и JSON в docs/architecture. Подробные measurements/build/native limitations — единый отчёт6.

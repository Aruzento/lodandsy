# Компоненты локального W2 preflight

Это инвентаризация проверенного прототипа, не публичный release и не юридическое
заключение о готовности распространения. Компоненты динамически загружаются из
_internal; исходные библиотеки не изменены. Source приложения и сценарий пересборки
включены. Лицензии приложения владелец пока не задавал; публикация не выполнялась.

| Компонент | Версия | Лицензия/источник |
| --- | --- | --- |
| CPython | 3.14.8 | PSF; LICENSES/Python-LICENSE.txt, https://www.python.org/ |
| Qt / PySide6-Essentials / shiboken6 | 6.11.2 | Metadata: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; тексты LGPLv3/GPLv3 приложены; https://pypi.org/project/PySide6-Essentials/6.11.2/ |
| Qt ADS / Python bindings | 5.1.1 | LGPL 2.1 и MIT notice первоначальных bindings, тексты приложены; https://pypi.org/project/PySide6-QtAds/5.1.1/ |
| PyInstaller bootloader | 6.22.3 | GPLv2 с исключением для собранных приложений; https://pyinstaller.org/en/stable/license.html |

Первичный PyPI PySide6 сообщает, что wheel подходит для open source и commercial use.
В wheel 6.11.2 license directory содержит коммерческий текст при OSS metadata;
поэтому open-source тексты взяты непосредственно из Qt qtbase tag v6.11.2:
https://github.com/qt/qtbase/tree/v6.11.2/LICENSES . Это не означает наличие у владельца
коммерческой лицензии и не требует выбора коммерческого режима для этого прототипа.

Исходники библиотек: https://code.qt.io/cgit/pyside/pyside-setup.git/ ,
https://github.com/qt/qtbase/tree/v6.11.2 ,
https://github.com/mborgerson/pyside6_qtads и source distribution версии 5.1.1 на PyPI.
Перед публичной поставкой нужны окончательная инвентаризация Qt/third-party компонентов,
полные notices, выбранная лицензия приложения и выполнение применимых обязательств
LGPL, включая возможность замены совместимых динамических библиотек. Это отдельная
проверка ARU-63/64, не подменённая наличием данного файла.

Windows ICU — системная зависимость, не включена. Ошибочно подобранный упаковщиком
ICU-78 с несовместимыми экспортами исключён из spec; Qt использует системную ICU.
Microsoft VC runtime файлы поступили из CPython/Qt wheel; отдельная установка runtime
не выполнялась. Набор DLL подтверждается содержимым _internal.

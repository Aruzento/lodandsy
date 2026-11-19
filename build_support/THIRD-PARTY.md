# Компоненты кандидата LODANDSY MVP

Локальный кандидат для проверки, не публичный release. Лицензию собственного приложения
владелец ещё не выбрал; эта упаковка не делает такой выбор за него.

| Компонент | Проверенная версия | Лицензия / исходники |
| --- | --- | --- |
| CPython | 3.14.8 | PSF; `LICENSES/Python-LICENSE.txt`; https://www.python.org/ |
| Qt / PySide6 / shiboken6 | 6.11.2 | LGPLv3/GPL; `LICENSES/`; https://code.qt.io/cgit/pyside/pyside-setup.git/ и https://github.com/qt/qtbase/tree/v6.11.2 |
| Qt ADS / Python bindings | 5.1.1 | LGPLv2.1 / MIT notice; `LICENSES/Qt-ADS-LGPL-2.1.txt`, `PySide6-QtAds-NOTICE.txt`; https://pypi.org/project/PySide6-QtAds/5.1.1/ |
| PyInstaller bootloader | 6.22.3 | GPLv2 с исключением для приложений; https://pyinstaller.org/en/stable/license.html |
| pyvips | 3.2.0 | MIT; `LICENSES/libvips/pyvips-LICENSE.txt`; https://github.com/libvips/pyvips |
| pyvips-binary / native libvips | 8.18.7 | LGPLv3 aggregate, MIT wrapper; `LICENSES/libvips/`; https://github.com/kleisauke/pyvips-binary |
| cffi / pycparser | 2.1.1 / 3.12 | MIT/BSD; `LICENSES/libvips/`; https://github.com/python-cffi/cffi / https://github.com/eliben/pycparser |

Native libvips распространяется отдельной заменяемой DLL. SHA256 DLL проверен с
официальным `libvips-8.18.7-win-x64.tar.gz`; точные versions, aggregate notices,
LGPL2.1/3 и MIT/BSD тексты, URL исходников и build recipes находятся в `LICENSES/`.
Набор зависит от статически включённых в эту DLL библиотек: версии перечислены
в `Vips-versions.json`, исходные notices сохранены без редактирования. Для замены
соберите libvips с совместимым ABI42/API8.18 и `_libvips.pyd` либо пересоберите package
из приложенного source с согласованными wheels. Ограничения отладки этих библиотек
не вводятся. PSUtil используется только отдельным прототипом измерений и не входит
в приложение. NASA benchmark images не включаются в дистрибутив и source.

Библиотеки динамические и не изменены; совместимые DLL/PYD в `_internal` можно заменить
и пересобрать приложение из приложенного `source/`. Обновлять Qt/ADS нужно совместно,
после повторной проверки. Qt OSS license texts взяты из официального qtbase v6.11.2:
https://github.com/qt/qtbase/tree/v6.11.2/LICENSES . Wheel metadata допускает OSS;
наличие коммерческого текста в wheel не означает приобретение коммерческой лицензии.
См. также https://pypi.org/project/PySide6/6.11.2/ .

ICU используется из Windows, ICU78 не распространяется. VC runtime поступает из
CPython/Qt wheels. Перед публичным распространением остаются полная инвентаризация
вложенных third-party notices и проверка обязательств LGPL для выбранного способа
поставки. Эта запись фиксирует проверенные компоненты и не является юридическим заключением.

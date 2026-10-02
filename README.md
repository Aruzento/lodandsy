# LODANDSY

LODANDSY — desktop-приложение на Python и PySide6.

## Требования

- Windows
- Python 3.14

## Подготовка окружения

Создать виртуальное окружение:

```powershell
py -3.14 -m venv .venv
```

Активировать его:

```powershell
.\.venv\Scripts\Activate.ps1
```

Установить приложение и зависимости разработки:

```powershell
python -m pip install -e ".[dev]"
```

## Запуск

```powershell
python -m lodandsy.main
```

## Проверки

Запустить тесты:

```powershell
python -m pytest
```

Проверить код через Ruff:

```powershell
python -m ruff check .
```
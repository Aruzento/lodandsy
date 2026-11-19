# ARU-70 — воспроизводимый Windows-прототип

Это сравнительный прототип, не новая готовая версия Map. Production16MP/64MiB пока
сохранены. Результаты и предлагаемая архитектура: `docs/adr/011-large-map-proposal.md`.

В корне checkout, Python3.14.8:

```powershell
python -m venv .prototype-deps/map-preflight-venv
.prototype-deps/map-preflight-venv/Scripts/python.exe -m pip install -r prototypes/requirements-large-map.txt
.prototype-deps/map-preflight-venv/Scripts/python.exe prototypes/large_map_preflight.py generate .prototype-deps/large-map-100mp.png --edge 10000
.prototype-deps/map-preflight-venv/Scripts/python.exe prototypes/large_map_preflight.py vips .prototype-deps/large-map-100mp.png --output .prototype-deps/my-pyramid
.prototype-deps/map-preflight-venv/Scripts/python.exe prototypes/large_map_preflight.py qt .prototype-deps/large-map-100mp.png --qt-allocation-mib 512
.prototype-deps/map-preflight-venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath .prototype-deps/map-preflight-dist --workpath .prototype-deps/map-preflight-qt-isolated-build prototypes/large_map_preflight.spec
.prototype-deps/map-preflight-dist/LODANDSY-Map-Preflight-Qt/LODANDSY-Map-Preflight-Qt.exe compat .prototype-deps/my-frozen-smoke
```

Используйте новые output names: prototype dzsave не предназначен для замены ресурсов
проекта. `generate` создаёт синтетический raster. `qt` с512MiB — намеренный замер
недостатка ClipRect на PNG, не изменение лимита продукта. `compat` создаёт Qt ADS manager,
запускает libvips, читает полученный tile Qt и проверяет размер/цвет. Console exit0 и
JSON — подтверждение автоматического smoke, не mouse/DPI или clean-Windows приёмки.

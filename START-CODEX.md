# Активная итерация6-rev3

Выполнить целиком утверждённый пакет docs/iterations/2026-11-19-iteration-6-rev3/CODEX-ITERATION-6.md
последовательно A→E, без промежуточных согласований. Baseline be24ec2, CI44563513498.
Архитектурный приоритет — функциональные границы ARU-84 (ADR-027), затем inventory refs,
нейтральный Qt layout по private макетам и исправления. Бинарные макеты/portrait находятся
только в .prototype-deps/iteration6-rev3-reference, не публиковать/не включать в поставку.
Core EntitySession + Cards/Tables/Maps services/controllers + DiceController, explicit root
wiring, общие ProjectResources/MediaService, cross-feature ProjectActions; ModuleController/
ModuleSession/ApplicationSession/CardImages удаляются. Сохранить S3/ADS/libvips/Qt HTML.
Targeted batches на функциональных границах, полный итоговый gate/Windows build после
стабилизации, единый отчёт/архитектура.drawio/checklist. Git-действия только в конце после
финальной проверки по последним указаниям владельца; публичного release нет.

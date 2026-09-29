# Общая модель содержания

Одинакова для `cgu-original-deck/1` и `cgu-presentations/2`. Сначала фиксируйте содержание и источники, затем связывайте их с выбранной композицией. Полный контракт: `schemas/content-model.schema.json`, исполняемые проверки: `scripts/content_model.py`.

В корне deck: `sources` и `content_model: {schema_version: "cgu-content/1", sources: [...], items: [...]}`. Оба списка sources должны совпадать. Каждый источник имеет уникальный id и location (файл/страница/ячейка), расчёт — status calculated и formula, конфликт — status conflict и блокирует использование до разрешения.

Минимальный item:

```json
{"id":"fact-1","kind":"fact","claim_type":"source_report","value":"Обращения принимаются онлайн","source_ids":["report"]}
```

На слайде укажите `source_ids: ["report"]`, `object_sources: {"/fields/ph-0": ["report"]}` и `model_bindings: [{"pointer":"/fields/ph-0","content_id":"fact-1"}]`. Значение поля должно точно совпадать с value. Для semantic используется, например, `/title`, `/items/0/body`, `/series/0`. Включите `evidence_policy: object` для адресуемости всех значимых объектов. ID поля ph-0 — пример: реальные ключи берите из каталога или original-init.

Виды items: claim, fact, kpi, assumption, quotation, interpretation, speaker_note, appendix_candidate, chart_series, categories, node, relationship. Типы утверждений: fact, source_report, assumption, quotation, interpretation. Для assumption/interpretation нужен rationale. speaker_note связывается через note_ids, остальные видимые элементы — model_bindings. Неиспользованный item требует disposition excluded с reason. Связи и источники попадают в настоящие Notes PPTX, отдельно от редакторских заметок.

KPI содержит шесть строк: value, unit, currency, sign, period, comparison_base. Видимое value равно sign + currency + value (например, `−36 млн`). Каждый компонент имеет `source_components` со source_id и pointer на предоставленный снимок данных источника. Отсутствующий период/базу обозначайте как неизвестные, не выдумывайте. Контекст KPI должен присутствовать на слайде. Изменение знака, единицы, валюты, значения, периода или базы вызывает ошибку. Существующие колоды без content_model сохраняют прежний контракт; новая полная проверка не применяется к ним задним числом.

Проверка отдельной модели: `python3 scripts/run.py content-validate model.json`. Проверка колоды: `python3 scripts/run.py validate deck.json`. Это контроль связности предоставленных данных, не внешняя проверка истинности.

Журнал исходного содержания описан в [content-review.md](content-review.md). Решения: preserved, condensed, merged, moved_to_appendix, excluded (старый appendix также принимается). Для сокращения сохраняйте исходный и итоговый текст, для исключения — причину. Сборка выдаёт content/storyboard.json, content/content-model.json, qa/content-model.json и отчёт ledger.

`readiness_policy`: experimental (совместимый режим по умолчанию), usable или production. Последние два отклоняют слайды ниже выбранного уровня. У semantic-композиций в этом выпуске нет production-приёмки. Разрешение experimental не является визуальным одобрением.

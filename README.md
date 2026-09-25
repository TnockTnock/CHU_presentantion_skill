# Презентации ЦГУ

Переносимый скилл в формате Agent Skills: подготовка содержания, сборка PPTX из фирменного шаблона ЦГУ, Golos Text, редактируемые схемы, графики и таблицы. Результат: PPTX и сценарий; при наличии рендерера также PDF и PNG. Основной portable-сборщик требует только Python 3.9+. Специальный Codex backend сохранён.

## Разные агенты и модели

[Подключение и ограничения](skills/cgu-presentations/references/portability.md). Один пакет для Claude Code, Cursor, Gemini CLI, GitHub Copilot, Codex и агентов, умеющих читать файлы и запускать Python. Название модели не передаётся сборщику; качество подготовки содержания зависит от модели.

```bash
python3 skills/cgu-presentations/scripts/skill_package.py install --agent claude --project /path/to/project
python3 skills/cgu-presentations/scripts/skill_package.py pack --out work/cgu-presentations.zip
python3 skills/cgu-presentations/scripts/run.py demo --backend portable --no-render --out work/portable-demo
```

Для другого агента замените `claude` на `cursor`, `gemini`, `copilot`, `codex` или `generic`. Для обновления используйте `--replace`, который сохраняет резервную копию. Клиентские профили установки проверены на уровне файлов; запуск всех продуктов и всех моделей не заявляется.

## Быстрый тест

Из корня репозитория:

```bash
python3 -m unittest discover -s tests -v
python3 skills/cgu-presentations/scripts/run.py doctor --backend portable
python3 skills/cgu-presentations/scripts/run.py demo --backend portable --no-render --out work/demo-01
```

Для этого теста нужен только Python 3.9+. Для PDF и PNG уберите `--no-render` и установите LibreOffice и Poppler. В Codex используется bundled рендерер. `doctor` показывает найденные пути; выбор движка описан в [инструкции сборщика](skills/cgu-presentations/references/builder.md).

Демонстрация содержит 7 слайдов: обложку, 4 карточки, KPI, процесс, архитектурную схему, нативный график и таблицу. Данные явно помечены как демонстрационные. Для проверки обычного текста и нулевых/отрицательных значений есть `examples/edge-cases.json` внутри скилла.

## Работа со своими материалами

Вызов установленного скилла в Codex:

> Используй $cgu-presentations. Подготовь презентацию на 8 слайдов для руководства ДИТ по приложенному отчёту. Используй наш шаблон, Golos Text и редактируемые схемы.

Агент изучает материал, создаёт структуру и JSON по [контракту](skills/cgu-presentations/references/builder.md), запускает сборщик и просматривает каждый слайд. Сам CLI не извлекает смысл из произвольного отчёта: его вход — подготовленная спецификация.

```bash
python3 skills/cgu-presentations/scripts/run.py build deck.json --out work/my-deck-01
```

Каждый запуск использует новую папку. Итоговые файлы в `output/`, проверка в `qa/`, картинки в `preview/`. Каталог `work/` исключён из Git. Для реальных презентаций не включайте `demo: true`; источники обязательны.

## Установка и обновление

Попросите Codex: «Установи скилл из TnockTnock/CHU_presentantion_skill, путь skills/cgu-presentations». Стандартный skill-installer устанавливает отдельную копию в пользовательскую папку скиллов. Она будет доступна со следующего сообщения. Правки локального репозитория не обновляют установленную копию автоматически: после обновления кода синхронизируйте её и проверьте совпадение файлов.

Для разработки можно прямо указать агенту локальный `skills/cgu-presentations/SKILL.md` без установки. GitHub и локальный репозиторий синхронизируются через Git: `git pull --ff-only`, ветка `codex/<задача>`, тесты, commit и push. Рабочая версия скилла находится здесь, а не в старом архиве рядом с репозиторием.

## Возможности и границы

- Автоматическая сборка 12 типов: cover, cards, kpi, text, process, diagram, chart, table, kpi_grid, comparison, roadmap, text_blocks (6 вариантов).
- Используются проверенные страницы 6, 8, 14, 15 короткого шаблона, исходные логотипы и размер 1440×810 pt. SHA-256 защищает адаптер от незаметной смены шаблона.
- Полный шаблон на 82 страницы сохранён как дополнительная библиотека. Автоматическое заполнение всех его макетов пока не поддерживается.
- Генераторы изображений не требуются для базовой сборки. Иллюстрации и дополнительные макеты добавляются агентом отдельным расширением, с проверкой.
- Текст измеряется перед экспортом. Схемы содержат связанные фигуры и стрелки. Графики содержат данные и workbook snapshot; таблицы остаются нативными.
- Шрифты PPTX не встроены. Для редактирования нужны Golos Text Regular/SemiBold/Bold из пакета. Для просмотра на другом компьютере используйте проверенный PDF.
- Структурная и визуальная проверка не равна ручному тесту редактирования в Microsoft PowerPoint. Такой тест ещё не проводился.

## Состав

`skills/cgu-presentations/` содержит точку входа SKILL.md, правила, шаблоны, шрифты, примеры JSON и скрипты. `tests/` — автономные Python-тесты. `docs/validation.md` — запись проведённой проверки без пользовательских материалов.

Лицензия Golos Text находится рядом со шрифтами. Корпоративные шаблоны и логотипы не объявляются свободно лицензированными этим репозиторием; условия использования определяет правообладатель.

## Библиотека референсов

[Правила библиотеки](skills/cgu-presentations/references/library.md) описывают локальный каталог и переносимые композиции. `design-system/layouts.json` хранит исполняемые привязки; `tokens.json` — параметры оформления; `reference-patterns.json` — 16 отобранных семейств композиций без внутренних данных.

Новые макеты и подписи связей: `python3 skills/cgu-presentations/scripts/run.py build skills/cgu-presentations/examples/library-demo.json --out work/library-demo`. Исходные презентации, извлечённый текст и их превью остаются в игнорируемом `work/` либо вне репозитория. Персональный `skills/cgu-presentations/local/reference-library.json` также исключён из Git.

## Текстовые шаблоны

[Шесть композиций и правила выбора](skills/cgu-presentations/references/text-blocks.md) · [PPTX](skills/cgu-presentations/assets/library/text-blocks.pptx) · [PDF](skills/cgu-presentations/assets/library/text-blocks.pdf)

Заголовки — SemiBold 600, цифры — Bold 700, основной текст — Regular 400. В переносимых шаблонах только нейтральные тексты и вымышленные показатели. Сборка всех вариантов:

```bash
python3 skills/cgu-presentations/scripts/run.py build skills/cgu-presentations/examples/text-blocks-demo.json --out work/text-blocks
```

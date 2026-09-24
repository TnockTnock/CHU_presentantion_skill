# Один скилл для разных агентов и моделей

## Возможности среды

Скилл использует общий формат [Agent Skills](https://agentskills.io/specification): `SKILL.md`, относительные ссылки, скрипты и ассеты. Модель отвечает за содержание и выбор композиции; сборщик получает JSON и не вызывает API моделей. Платная подписка конкретного провайдера для сборки не нужна.

Определи возможности текущего агента до начала работы:

| Доступ | Результат |
|---|---|
| Файлы, Python 3.9+, запуск команд | PPTX, сценарий и структурные проверки через `--backend portable --no-render` |
| То же + LibreOffice и Poppler | Дополнительно PDF и PNG |
| Просмотр изображений | Можно выполнить визуальную проверку каждого PNG |
| Только текстовый чат | План и JSON по контракту, команды для локальной сборки; не заявляй, что PPTX создан |
| Codex с установленным Presentations runtime | Существующий backend `codex` с artifact-tool/finalizer |

`auto` сначала проверяет наличие полного Codex runtime, иначе выбирает `portable`. Явный `--backend portable` не загружает внутренние библиотеки Codex. Если выбранный backend падает при сборке, ошибка возвращается пользователю: незаметного переключения после ошибки нет.

Portable поддерживает все 12 типов `/2`, включая шесть `text_blocks`, нативные таблицы и графики с XLSX, связанные фигуры схем и заметки с источниками. Он работает с копией того же корпоративного PPTX и проверяет SHA. Пиксельное совпадение двух движков не гарантируется. Переносы и маршруты связей нужно смотреть в итоговых PNG.

## Подключение

Установщик запускается из любой копии скилла. `--project` — папка проекта, в котором агент должен видеть скилл. Он создаёт только каталог скилла, не меняет системные промпты, ключи, настройки моделей или чужие AGENTS.md/CLAUDE.md.

```bash
python3 scripts/skill_package.py install --agent claude --project /path/to/project
python3 scripts/skill_package.py install --agent cursor --project /path/to/project
python3 scripts/skill_package.py install --agent gemini --project /path/to/project
python3 scripts/skill_package.py install --agent copilot --project /path/to/project
python3 scripts/skill_package.py install --agent codex --project /path/to/project
```

| Профиль | Каталог внутри проекта | Основание |
|---|---|---|
| claude | `.claude/skills/cgu-presentations` | [Claude Code](https://code.claude.com/docs/en/skills) |
| cursor | `.cursor/skills/cgu-presentations` | [Cursor](https://cursor.com/docs/skills) |
| gemini | `.gemini/skills/cgu-presentations` | [Gemini CLI](https://geminicli.com/docs/cli/skills/) |
| copilot | `.github/skills/cgu-presentations` | [GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) |
| codex / generic | `.agents/skills/cgu-presentations` | Общая локальная структура Agent Skills; путь зависит от клиента |

Для другого клиента укажи точную папку: `install --dest /path/to/skills/cgu-presentations`. Для обновления добавь `--replace`: старая папка сохраняется вне каталога обнаружения скиллов; персональная `local/` переносится в новую копию. Другие изменения старой установки остаются в резервной копии, а не переносятся автоматически. Без `--replace` существующая установка не меняется.

Для агента без обнаружения скиллов дай ему путь к SKILL.md и поручение: «Прочитай этот скилл, используй ресурсы рядом с ним и выполни задачу». Не вставляй в системный промпт содержимое пользовательских презентаций.

## Переносимый ZIP

```bash
python3 scripts/skill_package.py pack --out /path/to/cgu-presentations.zip
```

Архив содержит одну папку `cgu-presentations`. Сохраняй её структуру при распаковке. `local/`, кэши, рабочие отчёты и оригиналы референсов в архив не входят. В чатах с загрузкой ZIP распакуй его в среде выполнения и открой SKILL.md; возможность установки ZIP как навыка зависит от конкретного продукта и тарифа. Загрузка файла сама по себе не добавляет агенту выполнение кода.

## Сборка без Codex

В папке скилла:

```bash
python3 scripts/run.py doctor --backend portable
python3 scripts/run.py validate examples/demo.json
python3 scripts/run.py demo --backend portable --no-render --out /path/to/new-demo
python3 scripts/run.py build /path/to/deck.json --backend portable --out /path/to/new-deck
```

На Windows используй `py -3` вместо `python3`, если так установлен Python; относительные пути работают и в PowerShell. Все текстовые артефакты читаются и записываются в UTF-8. Пути к внешним программам можно задать переменными `CGU_SOFFICE` и `CGU_PDFTOPPM` — полный путь к исполняемому файлу, включая `.exe` на Windows. Иначе они ищутся в PATH. В среде Codex при наличии bundled runtime его рендерер имеет приоритет над desktop LibreOffice.

Установи Golos Text Regular/SemiBold/Bold из `assets/fonts` в среде рендеринга. Fontconfig в Linux/macOS получает локальную конфигурацию автоматически; Windows-рендереру может требоваться установка TTF в системе. `--no-render` не требует установки шрифтов: для измерений читаются поставленные TTF. Результат при этом визуально не проверен.

Основной PPTX-сборщик portable не требует pip/npm. Только каталогизация внешних референсов использует дополнительные `pypdf` и `Pillow`, а также рендереры; она не нужна для использования готовой библиотеки.

## Границы проверки

Профили установки проверяются файловыми тестами. Это не означает, что каждый продукт был запущен и каждая модель проверена. Текущая локальная проверка portable выполнена на macOS; Windows/Linux предусмотрены переносимым кодом, но требуют собственного прогона. Отсутствие API-вызовов моделей делает сборщик независимым от модели, однако качество структуры и фактологии остаётся ответственностью агента. Не обещай одинаковое качество всем моделям.

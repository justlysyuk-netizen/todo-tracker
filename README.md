# Трекер задач

Личная доска задач на GitHub Pages: что делаю я и что делает Claude, в реальном времени, с полной историей.

- **Доска**: «Сейчас в работе», колонки Очередь / В работе / Заблокировано / Готово, прогресс по шагам.
- **История**: лента всех событий по дням (создал, взял в работу, шаг готов, заметка, блокировка, готово).
- **Живое обновление**: страница опрашивает GitHub API каждые 15 секунд. Пока ничего не меняется, запросы не расходуют лимит GitHub.
- Ссылки на задачу: `…/#task-7`, на историю: `…/#history`.

## Как это устроено

Все задачи лежат в одном файле `data/tasks.json`. Любое изменение = коммит в репозиторий, поэтому `git log` тоже показывает историю разработки.

## Редактирование со страницы

Шестерёнка → вставьте GitHub‑токен (Fine‑grained, доступ только к этому репозиторию, право **Contents: Read and write**). После этого появятся кнопка «+ Задача», смена статуса, отметка шагов и заметки. Токен хранится только в вашем браузере.

## Командная строка (её использует Claude)

```bash
python3 scripts/tracker.py add "Название" --project наука --tags видео --steps "Шаг 1" "Шаг 2" --start   # печатает номер
python3 scripts/tracker.py add "Монтаж" --who Илья --steps "Картинки" "Тайминг" "Экспорт"
python3 scripts/tracker.py start 7
python3 scripts/tracker.py step 7 1          # шаг 1 готов (можно несколько: step 7 2 3)
python3 scripts/tracker.py progress 7 40 --note "60 из 150 промптов"
python3 scripts/tracker.py note 7 "что сделано"
python3 scripts/tracker.py add-step 7 "Новый шаг"
python3 scripts/tracker.py block 7 "что мешает"
python3 scripts/tracker.py queue 7
python3 scripts/tracker.py done 7 --note "итог"
python3 scripts/tracker.py reopen 7 --start
python3 scripts/tracker.py edit 7 --title "Новое название" --project potolki
python3 scripts/tracker.py list [--all] [--status blocked]
python3 scripts/tracker.py show 7
```

Каждая команда сама делает `git pull`, коммит и `git push` (с повтором при конфликте). `--no-push` только меняет файл, `--by Илья` подписывает запись другим автором.

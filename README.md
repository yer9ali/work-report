# work-report

Плагин Claude Code: карточки выполненных задач за день и недельный отчёт по регламенту.
Источники — git-коммиты и история сессий Claude Code. Ничего не отправляется в таск-трекер,
результат — только текст.

## Установка
```
/plugin marketplace add https://github.com/yer9ali/work-report.git
/plugin install work-report@work-report
```
Обновление: `/plugin update work-report@work-report`.

## Вызов
- `/work-report` — карточки за сегодня;
- `/work-report 2026-10-06` — карточки за указанный день;
- `/work-report week` — недельный отчёт по регламенту.

При конфликте имён используйте `/work-report:work-report`.

## Первый запуск и конфиг
Если конфига нет, скрипт завершается с кодом 3, а Claude предлагает авторов из
`digest.py --suggest-authors` (у человека часто несколько email: машинный, рабочий,
GitHub/GitLab) и создаёт `~/work-reports/config.json`:
```json
{
  "authors": ["Имя <me@example.com>"],
  "reports_dir": "~/work-reports",
  "extra_repos": [],
  "exclude_paths": []
}
```
- `authors` — обязательно, непустой список строк; иначе код выхода 3;
- `reports_dir` — каталог журнала (по умолчанию `~/work-reports`);
- `extra_repos` — дополнительные репозитории, учитываются без сессий Claude Code;
- `exclude_paths` — пути, которые игнорируются (`~/.claude-mem` исключён всегда).

Неверные даты или `--tz` дают код выхода 2.

## Где журнал
В `reports_dir`: `<дата>.md` — карточки дня, `week-<понедельник>.md` — недельный отчёт,
`products.json` — личный словарь продуктов.

## Общий словарь продуктов
Чтобы добавить продукт всем, отправьте MR/PR с правкой
`plugins/work-report/skills/work-report/reference/products.json`.

## Разработка
```
python3 -m pytest
ruff check .
claude plugin validate .
```

## Примеры
Пример дня и пример недели появятся здесь после первого реального прогона (пометка «пример»).

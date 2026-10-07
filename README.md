# work-report

Плагин Claude Code: карточки выполненных задач за день и недельный отчёт по регламенту.
Источники — git-коммиты и история сессий Claude Code (и claude-mem, если установлен).
Ничего не отправляется в таск-трекер, результат — только текст. Пароли, токены, ключи
и cookie маскируются ещё до того, как выжимка попадает в Claude.

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

## Конфиг (необязателен)
Свои коммиты определяются по `git config user.email` репозитория. Если коммитите и с другого
email, добавьте его в `~/work-reports/config.json`: `{"authors": ["old@example.com"]}`.
Там же можно задать `reports_dir`, `extra_repos` и `exclude_paths`.

## Регламент компании
В плагине лежит общий пример регламента. Свой положите в `~/work-reports/reglament.md` —
режим `week` будет писать отчёт по нему. Из Word на macOS:
```
textutil -convert txt -output ~/work-reports/reglament.md "Еженедельная отчетность.docx"
```
Файл остаётся только у вас и в репозиторий не попадает.

## Продукты
Отчёт группируется по продуктам. По умолчанию продукт = имя репозитория. Если в отчёте он
называется иначе, скилл спросит один раз и запишет в `~/work-reports/products.json`:
`{"pos_backend": "POS"}`. Номер задачи `[#142]` берётся из имени ветки или текста коммита.

## Где журнал
В `reports_dir`: `<дата>.md` — карточки дня, `week-<понедельник>.md` — недельный отчёт,
`products.json` — словарь продуктов, `reglament.md` — регламент компании.

## Разработка
```
python3 -m pytest
ruff check .
claude plugin validate .
```

## Примеры
Пример дня и пример недели появятся здесь после первого реального прогона (пометка «пример»).

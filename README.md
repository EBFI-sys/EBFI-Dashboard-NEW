# EBFI Ops

Внутренняя система EBFI Engineering Bureau International: заявки, работы (P&L по месяцам), инвойсы клиентам с GST, реестр TDS, счета инспекторов и дашборд. Заменяет четыре Google Таблицы с 1 декабря 2026.

## Из чего состоит

| Часть | Что это |
| --- | --- |
| `backend/` | API на Python (FastAPI + SQLAlchemy), база PostgreSQL 16 |
| `frontend/` | Интерфейс на React + TypeScript, раздаётся через Caddy с автоматическим HTTPS |
| `docker-compose.yml` | Три контейнера: `db`, `api`, `web` |
| `deploy/` | Установка, обновление и ежедневный бэкап |
| `backend/scripts/` | Создание пользователей и импорт ноября из Google Таблиц |

## Как считается P&L

B = (количество × ставка клиенту + overtime) × курс месяца, в INR.

| Показатель | Клиент из Индии | Клиент вне Индии |
| --- | --- | --- |
| Приход на счёт | B × 1,08 (+18% GST − 10% TDS) | B |
| GST (транзит, не выручка) | B × 0,18 | 0 |
| TDS (в реестр TDS, не расход) | B × 0,10 | 0 |
| Админка | B × 0,18 | B × 0,18 |
| Подряд | количество × ставка инспектору × курс | то же |
| РКО | по способу оплаты (пока 0) | то же |
| **Чистая прибыль** | **B − админка − подряд − РКО** | то же |

Выручка на дашборде = B. Ставки меняются в «Справочники → Ставки налогов». Курс за месяц админ вносит по RBI в последний день месяца; до этого используется курс прошлого месяца с пометкой. При закрытии месяца курс и ставки фиксируются в строках.

## Роли

| Роль | Что может |
| --- | --- |
| админ | всё, включая пользователей, удаление (мягкое) и повторное открытие месяца |
| бухгалтер | всё, кроме пользователей и удаления |
| менеджер | все данные, включая маржу, счета и статусы оплаты; без настроек и закрытия месяца |

Админ и бухгалтер обязаны включить двухфакторную аутентификацию. Каждое изменение пишется в журнал.

## Первая установка на сервер

Сервер: Ubuntu 24.04 с Docker (подготовлен скриптом `setup.sh`), пользователь `deploy`.

```bash
ssh deploy@206.189.135.219
sudo mkdir -p /opt/ebfi && sudo chown deploy:deploy /opt/ebfi
git clone https://github.com/EBFI-sys/EBFI-Dashboard-NEW.git /opt/ebfi/app
cd /opt/ebfi/app
bash deploy/install.sh                      # создаёт .env с секретами и запускает систему
docker compose exec api python -m scripts.create_admin   # печатает временные пароли
(crontab -l 2>/dev/null; echo "15 2 * * * /opt/ebfi/app/deploy/backup.sh >> /opt/ebfi/backup.log 2>&1") | crontab -
```

Для клонирования приватного репозитория GitHub спросит логин и пароль: логин — ваш GitHub, пароль — токен с правом Contents: Read.

## Импорт стартовых данных (октябрь и ноябрь 2026)

1. Скачать четыре Google Таблицы как Excel и назвать `pnl.xlsx`, `requests.xlsx`, `sales.xlsx`, `invoices.xlsx`.
2. Скопировать на сервер: `scp pnl.xlsx requests.xlsx sales.xlsx invoices.xlsx deploy@206.189.135.219:/opt/ebfi/app/import/`
3. Запустить:
   ```bash
   docker compose exec api python -m scripts.import_xlsx --reset \
     --pnl /data/import/pnl.xlsx --requests /data/import/requests.xlsx \
     --sales /data/import/sales.xlsx --invoices /data/import/invoices.xlsx
   ```

Что попадает в систему:

- строки P&L, заявки, инвойсы клиентам и счета инспекторов только за октябрь и ноябрь 2026 (`--months` меняет набор месяцев);
- справочник инспекторов — все, кто работал за всю историю таблицы, с объединением вариантов написания (`scripts/names.py` плюс ручной список `MANUAL_MERGE` в `import_xlsx.py`); варианты сохраняются в примечании инспектора;
- справочник клиентов — все названия за всю историю, каждое юрлицо отдельно;
- курсы USD и EUR за эти месяцы из колонки «$/€».

`--reset` стирает рабочие данные и справочники (пользователи остаются), поэтому команду можно повторять. Строки без Job number получают номер вида `БН-2026-11-1`. «Чья»: Л → LM, М → MB, С → SV, Лю → LR; Д, А, Т — архивные координаторы.

## Обновление

```bash
cd /opt/ebfi/app && bash deploy/update.sh
```

## Бэкапы

`deploy/backup.sh` каждую ночь сохраняет дамп базы, загруженные PDF и `.env` в `/opt/ebfi/backups` (30 дней). Плюс еженедельные снимки всего сервера в DigitalOcean. Восстановление базы:

```bash
docker compose exec -T db pg_restore -U ebfi -d ebfi --clean < /opt/ebfi/backups/db-2026-12-01.dump
```

Файл `.env` храните ещё и вне сервера: без `ENCRYPTION_KEY` банковские реквизиты инспекторов не расшифровать.

## Разработка локально

```bash
cd backend && pip install -r requirements.txt
DATABASE_URL=postgresql+psycopg://user@localhost/ebfi COOKIE_SECURE=false uvicorn app.main:app --reload
cd frontend && npm install && npm run dev   # http://localhost:5173, /api проксируется на :8000
```

Схема базы создаётся при старте. Изменения схемы после запуска — через миграции Alembic (добавляются вместе с первым таким изменением).

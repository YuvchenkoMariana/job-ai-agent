# Job AI Agent — Повний опис проекту по кожній лінії

> Цей файл — твій головний путівник по проекту.  
> Тут пояснено **кожен файл, кожну функцію, кожну важливу лінію** —  
> що вона робить, чому вона там, і як все це складається в одну систему.

---

## 📁 Структура проекту

```
job-ai-agent/
│
├── server/                  ← HTTP сервер (FastAPI)
│   ├── fast_api.py          ← ГОЛОВНИЙ файл сервера — всі API ендпоінти
│   ├── scraper.py           ← Selenium: відкриває браузер, скрейпить DOU
│   └── jobs_sync.py         ← Запис вакансій в БД (глобальний каталог)
│
├── backend/
│   ├── ai/
│   │   ├── cv_parser.py     ← Парсить текст CV → структурований об'єкт
│   │   ├── cv_classifier.py ← Визначає категорію DOU з CV (Python/PHP/...)
│   │   ├── enricher.py      ← Завантажує текст вакансії + викликає OpenAI
│   │   └── matcher.py       ← Порівнює CV з вакансіями → score + аналіз
│   └── db/
│       └── database.py      ← SQLAlchemy моделі + init_db() + міграції
│
├── protocol/python/
│   └── job.py               ← Dataclass JobDescriptionExtension / JobDescriptionList
│
├── client/
│   ├── index.html           ← Веб-інтерфейс (браузер)
│   ├── styles.css           ← Стилі
│   └── app.js               ← JavaScript логіка UI
│
├── chrome_extension/        ← Chrome розширення (скрейпить DOU у браузері)
│   ├── manifest.json
│   ├── content.js
│   └── popup.js
│
├── tests/                   ← Автоматичні тести (pytest)
├── conftest.py              ← Налаштування тестів (in-memory DB, без OpenAI)
└── requirements.txt         ← Список Python пакетів
```

---

## 🚀 Як запускається проект — точка входу

### Команда запуску:
```bash
python -m uvicorn server.fast_api:app --host 0.0.0.0 --port 8000 --reload
```

**Що тут відбувається рядок за рядком:**

| Частина команди | Пояснення |
|---|---|
| `python -m uvicorn` | Запускає uvicorn через Python модуль. Uvicorn — це ASGI веб-сервер (аналог gunicorn, але для async) |
| `server.fast_api:app` | Говорить uvicorn: "в папці `server`, у файлі `fast_api.py`, знайди об'єкт `app`" |
| `--host 0.0.0.0` | Слухати на всіх мережевих інтерфейсах (не тільки localhost) |
| `--port 8000` | Порт 8000 |
| `--reload` | При зміні файлів — автоматично перезапускати сервер (тільки для розробки) |

Після запуску:
- Браузер: `http://localhost:8000` → автоматично перенаправляє на `/ui/`
- API документація: `http://localhost:8000/docs`

---

## 📄 `server/fast_api.py` — Серце проекту

Це **головний файл**. В ньому живуть всі HTTP ендпоінти, логіка auth, черга для CV парсинг.

### Рядки 1–19: Імпорти стандартних бібліотек Python

```python
from __future__ import annotations
```
Дозволяє використовувати анотації типів у форматі рядків(`list[str]` замість `List[str]`).
Це потрібно для сумісності з Python 3.9 і нижче, але ми використовуємо 3.13 — тут це "захисна" практика.

```python
import concurrent.futures  # Future — об'єкт "обіцянки" результату з іншого потоку
import logging             # Логування (виводить повідомлення з часом і рівнем)
import hashlib             # SHA-256 хешування (для паролів та de-dup CV)
import hmac                # Безпечне порівняння хешів (захист від timing attacks)
import json                # Серіалізація/десеріалізація JSON
import os                  # Читання змінних оточення (os.getenv)
import queue               # Thread-safe черга (Queue) для CV парсингу
import secrets             # Генерація криптографічно стійких токенів
import threading           # Потоки (Thread) для фонового CV парсингу
```

```python
from datetime import datetime as _dt, timedelta as _td
```
`datetime` — для порівняння дат (наприклад, "ця вакансія старіша 4 годин?").  
Перейменовуємо в `_dt` і `_td` щоб не конфліктувати з іменами змінних.

```python
from pathlib import Path          # Зручна робота з шляхами файлів (Path / "client")
from contextlib import asynccontextmanager  # Для lifespan менеджера FastAPI
from dataclasses import dataclass # Декоратор для простих класів-контейнерів даних
from urllib.parse import urlencode # Перетворює dict → URL query string: {"a": 1} → "a=1"
from typing import Any, TYPE_CHECKING, cast  # Типи для IDE підказок
```

---

### Рядки 20–48: Імпорти фреймворків

```python
from sqlalchemy.orm import Session as OrmSession
```
SQLAlchemy — ORM бібліотека (Object-Relational Mapper).  
`Session` — це "з'єднання з БД" в термінах SQLAlchemy.  
Перейменовуємо в `OrmSession` щоб не конфліктувати з нашим локальним `Session`.

```python
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Depends
```
- `FastAPI` — клас застосунку
- `HTTPException` — кидає HTTP помилку (404, 422, 500 тощо)
- `UploadFile` — тип для завантаженого файлу (наш CV)
- `File` — маркер що параметр є файлом у form-data
- `Header` — читає HTTP заголовок запиту (наприклад `X-Auth-Token`)
- `Depends` — Dependency Injection: автоматично викликає функцію і підставляє результат

```python
from fastapi.middleware.cors import CORSMiddleware
```
CORS = Cross-Origin Resource Sharing.  
Дозволяє JavaScript з будь-якого домену робити запити до нашого API.  
Без цього браузер блокував би запити з `localhost:3000` до `localhost:8000`.

```python
from fastapi.staticfiles import StaticFiles
```
Дозволяє FastAPI роздавати статичні файли (HTML, CSS, JS) як звичайний файловий сервер.

```python
from fastapi.responses import RedirectResponse
```
HTTP redirect — відповідь зі статусом 307/302 яка каже браузеру "іди туди".

```python
from pydantic import BaseModel
```
Pydantic — бібліотека для валідації даних.  
`BaseModel` — батьківський клас для JSON схем (RegisterRequest, LoginRequest).  
FastAPI автоматично перетворює JSON body запиту в Pydantic модель.

---

### Рядки 29–47: Наші власні імпорти

```python
from backend.db.database import (
    Session,         # Фабрика сесій SQLAlchemy
    CvDocument,      # Модель таблиці cv_documents
    UsersCv,         # Модель таблиці users_cv (структурований CV)
    User,            # Модель таблиці users
    JobPosting,      # Модель таблиці job_postings (глобальний каталог вакансій)
    JobRun,          # Модель таблиці job_runs (знімок: CV + список вакансій)
    JobRunJob,       # Зв'язкова таблиця run ↔ job (many-to-many)
    MatchReportCache,    # Кеш загального звіту матчингу
    JobAnalysisCache,    # Кеш аналізу однієї вакансії
    init_db,         # Функція створення таблиць
    utc_now_minute,  # Поточний час UTC, округлений до хвилини
    GUEST_USER_UUID, # Фіксований UUID гостьового користувача
)
```

```python
from backend.ai.enricher import fetch_and_save_text, enrich_from_text
# fetch_and_save_text — завантажує HTML сторінку вакансії і зберігає текст
# enrich_from_text   — читає текст вакансії, дзвонить OpenAI, заповнює поля

from backend.ai.cv_classifier import classify_cv
# classify_cv — визначає DOU категорію з тексту CV (Python/PHP/PM/Product)

from backend.ai.cv_parser import parse_cv
# parse_cv — парсить сирий текст CV в структурований об'єкт ParsedCv

from backend.ai.matcher import rank_jobs, build_report, analyze_job
# rank_jobs    — сортує вакансії за score (CV vs вакансія)
# build_report — будує загальний звіт по топ N вакансіях
# analyze_job  — детальний аналіз однієї вакансії
```

```python
from protocol.python.job import JobDescriptionExtension, JobDescriptionList
# JobDescriptionExtension — базовий dataclass: job_title + source_url
# JobDescriptionList      — список вакансій + серіалізація/десеріалізація JSON

from server.jobs_sync import upsert_jobs
# upsert_jobs — INSERT OR UPDATE вакансій у глобальний каталог job_postings
```

```python
if TYPE_CHECKING:
    from backend.db.database import JobPosting as JobPostingType
```
`TYPE_CHECKING = False` в runtime, `True` тільки для IDE/mypy.  
Цей імпорт видно тільки для type checker-а — запобігає циклічним імпортам.

---

### Рядки 51–59: Логування

```python
logger = logging.getLogger(__name__)
```
Створює логер для цього модуля. `__name__` = `"server.fast_api"`.

```python
logging.basicConfig(
    level=logging.DEBUG,                             # Показувати все: DEBUG і вище
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    # Приклад виводу: 2026-05-08 12:00:01 [INFO] server.fast_api: ...
)
```

---

### Рядки 62–130: Фонова черга для CV парсингу

#### Чому черга, а не просто виклик функції?

`parse_cv()` може викликати OpenAI API — це мережевий запит, який займає **2–10 секунд**.  
FastAPI за замовчуванням запускає синхронні функції у thread pool (uvicorn робить це автоматично через `run_in_threadpool`).  
Але ми хочемо **явно контролювати**: один потік читає чергу і парсить по одному CV за раз.

```python
_cv_parse_queue: "queue.Queue[tuple[concurrent.futures.Future, str] | None]" = queue.Queue()
```
- `queue.Queue` — потокобезпечна черга (FIFO)
- В чергу кладемо пари: `(future, cv_text)`
- `future` — це "обіцянка" результату з бібліотеки `concurrent.futures`
- Спеціальне значення `None` в черзі — сигнал "зупинись" (sentinel)

```python
_cv_worker_thread: threading.Thread | None = None
```
Посилання на фоновий потік. `None` поки не стартований.

```python
def _cv_worker() -> None:
    while True:                               # Нескінченний цикл
        item = _cv_parse_queue.get()          # Блокує поки в черзі є елемент
        if item is None:                      # Сигнал зупинки
            _cv_parse_queue.task_done()
            break
        future, text = item                   # Розпаковуємо пару
        try:
            if future.set_running_or_notify_cancel():
                # set_running_or_notify_cancel() — каже Future "починаю виконання"
                # якщо Future вже скасована — повертає False і ми пропускаємо
                result = parse_cv(text)       # ТІЛЬКИ ТУТ викликається parse_cv
                future.set_result(result)     # Зберігаємо результат у Future
        except Exception as exc:
            try:
                future.set_exception(exc)     # Якщо помилка — передаємо в Future
            except Exception:
                pass                          # Future вже завершена — ігноруємо
        finally:
            _cv_parse_queue.task_done()       # Повідомляємо чергу: завдання виконане
```

```python
def _ensure_cv_worker_running() -> None:
    global _cv_worker_thread                  # Змінюємо модульну змінну
    if _cv_worker_thread is None or not _cv_worker_thread.is_alive():
        # Якщо потік ще не існує АБО він вже завершився → створюємо новий
        _cv_worker_thread = threading.Thread(
            target=_cv_worker,                # Функція яку виконує потік
            daemon=True,                      # daemon=True: потік зупиниться разом з main процесом
            name="cv-parser-worker"           # Ім'я для дебагу
        )
        _cv_worker_thread.start()             # Запускаємо
```

```python
def _parse_cv_queued(text: str, timeout: float = 120.0):
    fut: concurrent.futures.Future = concurrent.futures.Future()
    # Створюємо нову "обіцянку" — поки порожня
    _cv_parse_queue.put((fut, text))
    # Кладемо в чергу — worker потік забере і виконає parse_cv(text)
    return fut.result(timeout=timeout)
    # Блокуємо поточний потік і чекаємо результату максимум 120 секунд
```

---

### Рядки 131–150: Auth хелпери (паролі)

```python
_PBKDF2_ITERS = 120_000
```
PBKDF2 — алгоритм хешування паролів.  
120 000 ітерацій — це рекомендація NIST 2023.  
Чим більше ітерацій — тим повільніше атака брутфорсом.

```python
def _hash_password(password: str, salt_hex: str) -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256",               # Алгоритм хешу
        password.encode("utf-8"),  # Пароль в байтах
        bytes.fromhex(salt_hex),   # Сіль (16 випадкових байт)
        _PBKDF2_ITERS,             # Кількість ітерацій
    )
    return dk.hex()             # Повертаємо hex рядок довжиною 64 символи
```

```python
def _verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    got = _hash_password(password, salt_hex)
    return hmac.compare_digest(got, expected_hash_hex)
    # compare_digest — захист від timing attack:
    # завжди займає однаковий час незалежно від того чи пароль правильний
```

```python
def _new_token() -> str:
    return secrets.token_hex(32)  # 32 байти = 64 hex символи
    # secrets.token_hex — криптографічно стійкий генератор (не random!)
```

---

### lifespan — точка старту всього

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
```
`lifespan` — це async менеджер контексту.  
FastAPI викликає його при **старті** і **зупинці** сервера.

```python
    _ensure_cv_worker_running()   # Запускаємо фоновий потік CV парсингу
    init_db()                     # Створюємо таблиці в SQLite якщо не існують
    yield
    # ↑ Тут сервер ЖИВЕ і обробляє запити
    # ↓ Після yield — код зупинки (shutdown)
    _cv_parse_queue.put(None)     # Надсилаємо сигнал зупинки worker потоку
    if _cv_worker_thread is not None:
        _cv_worker_thread.join(timeout=5)  # Чекаємо до 5 секунд поки потік завершиться
```

**Чому `lifespan`, а не просто виклик в `main()`?**  
Бо uvicorn може бути запущений різними способами (напряму, через gunicorn, в тестах).  
`lifespan` гарантує що код ініціалізації запуститься в **будь-якому** режимі.

---

### Створення FastAPI застосунку

```python
app = FastAPI(title="Job AI Agent API", version="1.0.0", lifespan=lifespan)
```
Створюємо головний об'єкт. `lifespan=lifespan` — підключаємо наш startup/shutdown хук.

```python
_BASE_DIR = Path(__file__).resolve().parent.parent
_UI_DIR = _BASE_DIR / "client"
if _UI_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
```
- `Path(__file__)` — шлях до `server/fast_api.py`
- `.parent.parent` — підіймаємось два рівні вгору → корінь проекту
- `/ "client"` — Path-operator, додає `/client` до шляху
- `StaticFiles` — монтуємо папку `client/` під URL `/ui`
- Тепер `http://localhost:8000/ui/` роздає `client/index.html`

```python
@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui/")
```
GET запит на "/" → 307 редирект на "/ui/".  
`include_in_schema=False` — не показувати в `/docs`.

```python
app.add_middleware(CORSMiddleware,
    allow_origins=["*"],           # Дозволити всі домени
    allow_methods=["GET", "POST"], # Тільки ці HTTP методи
    allow_headers=["Content-Type", "X-Auth-Token"],  # Наш токен у заголовку
)
```

---

### Helper функції (утиліти)

```python
def _normalize_text(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")  # Windows → Unix переноси рядків
    t = "\n".join(line.rstrip() for line in t.split("\n"))  # Видаляємо trailing пробіли
    return t.strip()  # Видаляємо пробіли на початку і кінці
```
Нормалізуємо текст перед хешуванням — щоб однаковий CV, завантажений з Windows і Mac, давав однаковий hash.

```python
def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```
SHA-256 hash — 64-символьний рядок. Використовуємо для de-duplication CV та вакансій.

```python
def _jobs_hash_from_urls(urls: list[str]) -> str:
    uniq = sorted({(u or "").strip() for u in urls if (u or "").strip()})
    # Set comprehension → видаляємо дублікати і сортуємо (стабільний порядок)
    return _sha256_hex("\n".join(uniq))
    # Hash від відсортованого списку URL → ідентифікатор "набору вакансій"
```

```python
def _jobs_state_hash(session, job_ids: list[str]) -> str:
    # Враховуємо id + updated_at кожної вакансії
    # Якщо хтось оновив вакансію — hash зміниться → кеш аналізу стає недійсним
    rows = session.query(JobPosting.id, JobPosting.updated_at)
           .filter(JobPosting.id.in_(job_ids)).all()
    parts = sorted(f"{str(i)}:{str(ts or '')}" for i, ts in rows)
    return _sha256_hex("\n".join(parts))
```

---

## 🗄️ `backend/db/database.py` — База даних

### Константи

```python
GUEST_USER_UUID = "00000000-0000-0000-0000-000000000001"
```
Фіксований UUID для гостьового "користувача".  
Кожен незареєстрований запит до API обробляється від імені цього user.  
Це дозволяє тестам і Chrome extension працювати без реєстрації.

### UUID первинні ключі

```python
id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
```
- **Раніше**: `INTEGER AUTOINCREMENT` — БД сама генерує 1, 2, 3...
- **Тепер**: `String(36)` — Python генерує UUID типу `"a1b2c3d4-..."`  
- `default=lambda: str(uuid.uuid4())` — `lambda` обов'язкова! Якщо написати `default=str(uuid.uuid4())`, функція викличеться **один раз** при імпорті і всі записи матимуть однаковий ID

### Таблиці

#### `users` — користувачі
```
id             → UUID, PK
email          → унікальний, indexed (швидкий пошук)
password_salt  → 16 випадкових байт (hex), унікальний для кожного юзера
password_hash  → PBKDF2 hash пароля з цією сіллю
api_token      → 64 hex символи, унікальний — це "сесія" у браузері
created_at     → час створення (UTC, без секунд)
updated_at     → автоматично оновлюється при будь-якій зміні рядку
```

#### `users_cv` — структурований CV
```
id                → UUID, PK
user_id           → FK до users.id (UUID)
cv_hash           → SHA-256 від нормалізованого тексту CV
last_used_at      → коли останній раз завантажили цей CV
job_title         → бажана посада ("Python Developer")
all_text          → повний сирий текст CV
years_experience  → кількість років (float)
experience_bucket → "0-1", "1-3", "3-5", "5plus"
profile_summary   → "про себе"
programming_skills → мови, фреймворки
tools_and_tech    → інструменти
other_skills      → м'які навички, мови
projects          → опис проектів
education         → освіта
career_objective  → мета
additional_info   → додаткова інформація
```

#### `cv_documents` — сирі завантажені файли CV
Зберігаємо оригінальний текст окремо від розпарсеного CV.  
De-dup за `content_hash` — якщо завантажити той самий файл двічі, дублікат не створюється.

#### `job_postings` — глобальний каталог вакансій
```
id           → UUID, PK
source_url   → UNIQUE — ключ de-dup. Один URL = один запис для ВСІХ користувачів
job_title    → назва вакансії
full_text    → повний текст сторінки (після Step 2)
role_summary → короткий опис ролі (після Step 3 — OpenAI)
... + інші поля з OpenAI
```
> **Глобальний** означає: якщо юзер A і юзер B знайшли ту саму вакансію —
> вона зберігається **один раз** і збагачується OpenAI **один раз**.

#### `job_runs` — "знімок" пошуку
Кожного разу коли юзер завантажує CV і скрейпить DOU — створюється `JobRun`.  
Це дозволяє мати **історію пошуків**.

```
id                → UUID
user_id           → хто запустив
cv_id             → який CV використовувався
cv_hash           → hash CV (для smart reuse)
category          → яка DOU категорія ("Python")
experience_bucket → досвід ("0-1")
dou_url           → URL який скрейпився
jobs_hash         → hash набору вакансій (для кешування аналізу)
jobs_found        → скільки вакансій знайдено
synced            → скільки збережено
created_at        → час запуску
```

#### `job_run_jobs` — many-to-many: Run ↔ JobPosting
```
run_id  → FK до job_runs.id
job_id  → FK до job_postings.id
```
Один `job_run` може містити 50 вакансій.  
Одна вакансія може бути в 10 різних run-ах (різних користувачів).

#### `match_report_cache` та `job_analysis_cache`
Зберігають результати OpenAI аналізу щоб не платити двічі за один і той самий аналіз.  
Ключ кешу: `(user_id, cv_id, jobs_hash, method)`.  
Якщо будь-яка вакансія оновилась — `jobs_hash` зміниться → кеш стане недійсним.

### `init_db()` — ініціалізація БД

```python
def init_db() -> None:
    # 1. UUID міграція: якщо стара БД з INTEGER pk → видаляємо всі таблиці
    if "users" in tables:
        pk_col = ... # дивимося тип PK колонки
        if "INT" in pk_col.type.upper():
            # DROP TABLE для всіх таблиць (старі дані не сумісні з UUID)
            ...
    # 2. ADD COLUMN міграції (для UUID баз де може бракувати колонок)
    ...
    # 3. Base.metadata.create_all(engine) — створює таблиці якщо не існують
    # 4. Створює гостьового юзера з фіксованим GUEST_USER_UUID
```

---

## 🌐 API ендпоінти (server/fast_api.py продовження)

### Auth: реєстрація і логін

#### `POST /api/auth/register`
```
1. Валідація email (є "@")
2. Генерація salt: secrets.token_hex(16) → 32 символи
3. Хешування пароля: PBKDF2(password, salt, 120_000 ітерацій)
4. Перевірка унікальності email
5. Генерація api_token: secrets.token_hex(32) → 64 символи
6. Збереження в users
7. Відповідь: {user_id, email, token}
```

#### `POST /api/auth/login`
```
1. Знаходимо юзера за email
2. Перевіряємо пароль: PBKDF2(password, user.salt) == user.hash
3. Генеруємо НОВИЙ api_token (старий стає недійсним)
4. Відповідь: {user_id, email, token}
```

#### `get_current_user_id` — Dependency Injection
```python
def get_current_user_id(
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
) -> str:
```
FastAPI автоматично читає заголовок `X-Auth-Token` з кожного запиту.  
- Якщо заголовок відсутній → повертаємо `GUEST_USER_UUID`
- Якщо присутній → шукаємо юзера в БД → повертаємо його UUID
- Якщо токен невалідний → `HTTPException(401)`

Всі ендпоінти мають параметр `user_id: str = Depends(get_current_user_id)` —  
FastAPI сам викликає функцію і підставляє результат.

---

### Вакансії

#### `POST /api/jobs/sync`
Викликається Chrome розширенням після скрейпінгу DOU.

```
1. Отримуємо JobDescriptionList (JSON список вакансій з title + url)
2. upsert_jobs() → записуємо в job_postings (INSERT або UPDATE)
3. _create_or_reuse_run() → створюємо JobRun знімок
4. Відповідь: {"count": N}
```

#### `GET /api/jobs`
Повертає вакансії.
```
- ?run_id=UUID → тільки вакансії з конкретного run
- без параметрів → всі вакансії з усіх run-ів цього юзера (UNION)
```

---

### CV upload — Головний флоу

#### `POST /api/cv/run` — "Один клік"

Це найважливіший ендпоінт. Робить все одразу:

```
КРОК 1 — De-dup CV
  1a. Читаємо файл → декодуємо UTF-8
  1b. normalize_text() → sha256 → cv_hash
  1c. Шукаємо в cv_documents: user_id + content_hash
      → якщо є: UPDATE last_used_at
      → якщо нема: INSERT в cv_documents
  1d. Шукаємо в users_cv: user_id + cv_hash
      → якщо є: UPDATE last_used_at (пропускаємо parse_cv → економимо токени OpenAI)
      → якщо нема: _parse_cv_queued(text) → INSERT в users_cv

КРОК 2 — Класифікація
  2a. classify_cv(job_title) → category ("Python", "PHP" тощо)
  2b. Формуємо DOU URL: https://jobs.dou.ua/vacancies/?category=Python&exp=0-1

КРОК 3 — Smart reuse (оптимізація)
  3a. Чи є run з тим самим cv_hash + category за останні 4 години?
      → ТАК: повертаємо цей run (пропускаємо Selenium → економимо час)
      → НІ: продовжуємо

КРОК 4 — Selenium скрейпінг
  4a. scrape_and_sync(dou_url) → відкриває Chrome, клікає "показати ще", збирає URL
  4b. upsert_jobs() → записує в job_postings

КРОК 5 — Збереження знімку
  5a. _jobs_state_hash() → hash поточного стану вакансій
  5b. _create_or_reuse_run() → JobRun + JobRunJob записи

ВІДПОВІДЬ: {run_id, job_title, category, dou_url, scrape: {jobs_found, synced}}
```

---

### Match (матчинг CV з вакансіями)

#### `GET /api/match/scores`
```
1. Знаходимо latest CV юзера
2. Знаходимо latest run (або конкретний за run_id)
3. Отримуємо список job_ids з job_run_jobs
4. rank_jobs(cv, jobs) → список MatchItem відсортований за score
5. Відповідь: {total_jobs, items: [{job_id, job_title, score, reasons}]}
```

#### `GET /api/match/report`
```
1. Те саме що scores, але будує narrative звіт
2. Перевіряємо кеш: match_report_cache WHERE cv_id + jobs_hash + method
3. Якщо є кеш — повертаємо одразу (без OpenAI)
4. build_report(cv, ranked, jobs_by_id) → текстовий/OpenAI звіт
5. Зберігаємо результат в кеш
```

#### `GET /api/match/job/{job_id}/analysis`
```
1. Знаходимо конкретну вакансію
2. Перевіряємо job_analysis_cache (ключ: cv_id + job_id + job_updated_at)
3. Якщо кеш є і вакансія не змінилась — повертаємо кеш
4. analyze_job(cv, job) → детальний аналіз
5. Зберігаємо в кеш
```

#### `GET /api/history/runs`
Повертає список всіх попередніх run-ів юзера (для sidebar в UI).

---

### Step 2 і Step 3 — збагачення вакансій

#### `POST /api/jobs/fetch-text-all` (Step 2)
```
1. Беремо всі вакансії з поточного run де full_text IS NULL
2. Для кожної: fetch_and_save_text(job_id)
   → httpx.get(source_url) → BeautifulSoup → зберігаємо текст
3. Відповідь: {done: N, failed: M}
```

#### `POST /api/jobs/enrich-all` (Step 3)
```
1. Беремо вакансії де full_text IS NOT NULL і role_summary IS NULL
2. Для кожної: enrich_from_text(job_id)
   → OpenAI структурує текст → заповнює company_name, location, role_summary тощо
3. Відповідь: {enriched: N, failed: M}
```

---

## 🤖 `backend/ai/` — AI модулі

### `cv_parser.py` — Парсинг CV

Підтримує два режими:

**Heuristic (offline):**
```
- Регулярні вирази для email, телефону, GitHub/LinkedIn
- Пошук "X years" → years_experience → experience_bucket
- Назва посади: перший рядок або regex
```

**OpenAI (якщо OPENAI_CV_PARSER не `"0"`):**
```
- Надсилаємо весь текст CV в GPT
- Просимо повернути JSON з полями users_cv
- Парсимо відповідь → ParsedCv
```

`ParsedCv.to_sa_kwargs()` → повертає dict з полями для `UsersCv(**kwargs)`.

### `cv_classifier.py` — Класифікація категорії

```python
def classify_cv(cv_text: str) -> CvClassification:
```

**Heuristic:** Keywords matching:
- "python", "flask", "django" → `"Python"`
- "php", "laravel", "symfony" → `"PHP"`
- "project manager", "scrum master" → `"Project Manager"`
- etc.

**OpenAI (опціонально):** Надсилаємо заголовок CV, просимо вибрати категорію.

**Результат:**
```python
CvClassification(
    category="Python",      # DOU категорія
    job_title="Python Dev", # Назва посади з CV
    confidence=0.92,        # Впевненість (0..1)
    method="heuristic",     # Як визначили
)
```

### `enricher.py` — Збагачення вакансій

#### `fetch_and_save_text(job_id)`:
```python
# 1. Читаємо job.source_url з БД
# 2. Якщо full_text вже є → пропускаємо (кеш)
# 3. httpx.get(url) → отримуємо HTML сторінку
# 4. BeautifulSoup → видаляємо script/style/nav/footer → чистий текст
# 5. [:8000] → обрізаємо до 8000 символів
# 6. Зберігаємо в job_postings.full_text
```

#### `enrich_from_text(job_id)`:
```python
# 1. Читаємо job.full_text з БД
# 2. Якщо role_summary вже є → пропускаємо (кеш)
# 3. OpenAI gpt-4o-mini: надсилаємо текст вакансії
# 4. Просимо JSON з: company_name, location, work_type, role_summary,
#    responsibilities, required_quals, preferred_quals, tools_and_methods,
#    salary_min, salary_max, salary_currency, language_requirements
# 5. Зберігаємо поля в job_postings
```

### `matcher.py` — Порівняння CV з вакансіями

#### Як рахується score?

```python
def score_job(cv, job) -> MatchItem:
    cv_tokens  = tokenize(cv_text(cv))    # Токени з CV
    job_tokens = tokenize(job_text(job))  # Токени з вакансії
    common = cv_tokens & job_tokens        # Перетин (спільні слова)

    # Jaccard similarity: |common| / |cv ∪ job|
    jacc = len(common) / max(1, len(cv_tokens) + len(job_tokens) - len(common))

    # Бонус: назва категорії є в заголовку вакансії
    if "python" in job.job_title.lower(): jacc += 0.03

    # Бонус/штраф за досвід
    if cv.experience_bucket in {"0-1", "1-3"}:
        if "junior" in job_title: jacc += 0.05   # Підходить
        if "senior" in job_title: jacc -= 0.08   # Не підходить

    # Sigmoid → м'яке нормування в 0..1
    score = sigmoid((jacc - 0.08) * 10.0)
    return MatchItem(job_id=..., score=score, reasons=[...])
```

**Tokenizer:**
```python
def _tokenize(text: str) -> set[str]:
    # Регекс: слова довжиною ≥ 2 (включно з C++, C#)
    # Фільтруємо STOPWORDS: "the", "and", "та", "в", "experience" тощо
    # Lowercase
```

#### `_render_job_analysis_html` — HTML таблиця аналізу

Будує HTML таблицю:
```
| Requirement | CV match | Evidence |
|-------------|----------|---------|
| Python      | ✅       | mentioned in CV |
| Docker      | ❌       | not found in CV |
```

Перевіряє кожен skill pattern із списку `_SKILL_PATTERNS` (Python, Flask, Django, SQL, Docker, Git, AWS тощо).

---

## 🔄 `server/jobs_sync.py` — Upsert вакансій

```python
def upsert_jobs(payload: JobDescriptionList) -> list[str]:
```

Отримує список `{job_title, source_url}`.  
Для кожного:
```
source_url є в job_postings?
    ТАК → якщо title змінився → UPDATE job_title (not touching updated_at)
          → додаємо id до результату
    НІ  → INSERT new JobPosting
          → session.flush() → отримуємо UUID без commit
          → додаємо id до результату
session.commit()
```

`session.flush()` важливий — він записує в БД **без commit**.  
Це дозволяє отримати UUID нового запису, але якщо щось піде не так — можна зробити rollback.

---

## 🕷️ `server/scraper.py` — Selenium скрейпер

```python
def scrape_and_sync(url: str, *, headless: bool = True) -> ScrapeResult:
```

```
1. _build_driver(headless) → Chrome WebDriver
   - headless=True → браузер без вікна (для сервера)
   - webdriver_manager автоматично завантажує відповідний chromedriver
   
2. driver.get(url) → відкриваємо DOU сторінку

3. WebDriverWait → чекаємо поки завантажиться список вакансій
   (XPath: '//*[@id="vacancyListId"]/ul')

4. _click_show_more_until_gone() → цикл:
   - шукаємо кнопку "Показати ще"
   - scrollIntoView → клікаємо
   - sleep(1 секунда) → чекаємо AJAX підвантаження
   - повторюємо поки кнопка є

5. _iter_jobs() → для кожного <li>:
   - знаходимо перше посилання в div:nth-of-type(2)
   - беремо href + text
   - de-dup за URL
   - yield JobDescriptionExtension(job_title, source_url)

6. upsert_jobs(JobDescriptionList(jobs)) → записуємо в БД

7. driver.quit() → закриваємо браузер
```

---

## 📁 `protocol/python/job.py` — Протокол обміну даними

```python
@dataclass(frozen=True, slots=True)
class JobDescriptionExtension:
    job_title: str
    source_url: str
```
`frozen=True` → immutable (як tuple — не можна змінити після створення).  
`slots=True` → оптимізація пам'яті (замість `__dict__` використовує `__slots__`).

```python
class JobDescriptionList:
    jobs: list[JobDescriptionExtension]
    
    @classmethod
    def from_json(cls, data: str) -> "JobDescriptionList": ...
    def to_json(self) -> str: ...
```

Цей клас використовується і в Python сервері і (через TypeScript версію `protocol/js/job.ts`) в Chrome розширенні.  
Гарантує що формат даних між extension ↔ server однаковий.

---

## 🌍 Chrome Extension (`chrome_extension/`)

### `manifest.json`
```json
{
  "manifest_version": 3,
  "permissions": ["activeTab", "storage"],
  "content_scripts": [{ "matches": ["*://jobs.dou.ua/*"], "js": ["content.js"] }]
}
```
- `content_scripts` → `content.js` запускається автоматично на сторінках jobs.dou.ua
- `popup` → `popup.html/js` → маленьке вікно при кліку на іконку розширення

### `content.js`
- Слухає сторінку DOU
- Збирає всі `<a href>` з списку вакансій
- При натисканні кнопки в popup → відправляє зібрані вакансії на `POST /api/jobs/sync`

---

## 💻 `client/` — Веб інтерфейс

### `index.html` — структура сторінки

Сторінка складається з 4 карток (step flow):

```
Card 1 (#stepAccount)   → Register / Login / Guest
Card 2 (#stepCvUpload)  → Вибір файлу + кнопка Upload CV
Card 3 (#stepEnrich)    → Кнопки Start / Refresh jobs
Card 4 (#stepJobs)      → Список вакансій

Sidebar (col-right):    → Match score + звіт + аналіз по кліку
History sidebar:        → Попередні run-и (тільки для залогінених)
```

### `app.js` — логіка інтерфейсу

#### Ініціалізація (запускається при відкритті сторінки)
```javascript
// Очищаємо localStorage при кожному завантаженні сторінки
// → юзер завжди починає незалогінений (чисто)
localStorage.removeItem('authToken');
localStorage.removeItem('authEmail');
localStorage.removeItem('authUserId');
localStorage.removeItem('guestMode');
localStorage.removeItem('selectedRunId');

setAuthState();        // Встановлюємо стан UI
loadHistory();         // Завантажуємо history (тільки якщо є токен)
```

#### `apiJson(path, opts)` — всі запити до сервера
```javascript
async function apiJson(path, opts = {}) {
  const token = localStorage.getItem('authToken');
  // Якщо є токен → додаємо заголовок X-Auth-Token
  const headers = new Headers(opts.headers || {});
  if (token) headers.set('X-Auth-Token', token);
  
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!res.ok) { throw new Error(/* детальний опис помилки */); }
  return await res.json();
}
```

#### Step flow
```javascript
function setCurrentStep(step) {
  // step 0 → активна картка 1 (Account)
  // step 1 → картка 1 стає зеленою (done), активна 2 (Upload CV)
  // step 2 → картки 1,2 зелені, активна 3+4 (Enrich + Jobs)
  for (const card of STEP_CARDS) {
    if (card.step < step)  → клас "step-done"   (зелений)
    if (card.step === step → клас "step-active" (виділений)
    else                   → клас "step-future" (сірий)
  }
}
```

#### `uploadCv()` — завантаження CV
```javascript
async function uploadCv() {
  // 1. POST /api/cv/run?headless=1 з файлом у FormData
  // 2. Показуємо result: job_title, experience, category, DOU URL
  // 3. setCurrentStep(2) → активуємо картку Enrich
  // 4. loadHistory() → оновлюємо sidebar
  // НЕ викликаємо refreshJobs/refreshMatch автоматично
  // → юзер сам натискає Start
}
```

#### `runPipeline()` — натискання Start
```javascript
async function runPipeline() {
  // Step 2: POST /api/jobs/fetch-text-all
  // Step 3: POST /api/jobs/enrich-all
  // Після: refreshJobs() → показати список
  //        refreshMatch() → показати score
}
```

#### `getSelectedRunId()` — поточний run
```javascript
function getSelectedRunId() {
  return localStorage.getItem('selectedRunId') || null;
  // UUID рядок або null
  // Використовується для ?run_id= параметру в запитах
}
```

---

## 🧪 `tests/` — Тести

### `conftest.py` — глобальне налаштування тестів

```python
os.environ.setdefault("DB_URL", "sqlite:///:memory:")
```
Замість реального файлу `jobs_search.db` — **in-memory SQLite**.  
Кожен test run отримує чисту порожню БД. Зміни не зберігаються між тестами.

```python
os.environ.setdefault("OPENAI_CV_PARSER", "0")
os.environ.setdefault("OPENAI_CV_CLASSIFIER", "0")
```
Вимикаємо OpenAI — тести мають бути **детерміновані і офлайн**.

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```
Додаємо корінь проекту в `sys.path` → всі `import backend.xxx` та `import server.xxx` працюють.

### `tests/test_api.py`
Тестує API ендпоінти через `TestClient` (симульований HTTP клієнт, без реального сервера):
- GET `/api/jobs` → порожній список
- POST `/api/jobs/sync` → upsert → GET `/api/jobs` → список з 2 вакансій
- Перевірка всіх полів відповіді
- De-dup: той самий URL двічі → 1 запис

### `tests/test_match.py`
Тестує матчинг:
- Вставляємо CV + вакансії + run напряму в БД
- GET `/api/match/scores` → перевіряємо score в [0, 1]
- GET `/api/match/report` → перевіряємо summary
- GET `/api/match/job/{id}/analysis` → перевіряємо HTML таблицю

---

## ⚙️ `requirements.txt` — Залежності

```
fastapi          → Веб фреймворк (ендпоінти, валідація, docs)
uvicorn[standard]→ ASGI сервер (запускає FastAPI)
pydantic         → Валідація даних (BaseModel)
httpx            → Async HTTP клієнт (завантаження сторінок вакансій)
python-multipart → Підтримка file upload в FastAPI

sqlalchemy       → ORM для SQLite (моделі, сесії, запити)

openai           → Python SDK для OpenAI API (GPT)

selenium         → Автоматизація браузера (Chrome)
webdriver-manager→ Автоматичне завантаження chromedriver
beautifulsoup4   → HTML парсер (витягуємо текст з вакансій)
lxml             → Швидкий парсер HTML для BeautifulSoup

python-dotenv    → Читає .env файл → os.environ

pytest           → Фреймворк для тестів
pytest-asyncio   → Підтримка async тестів
```

---

## 🔑 Змінні оточення (`.env`)

Створи файл `.env` в корені проекту:

```env
# OpenAI
OPENAI_API_KEY=sk-...           # Твій ключ OpenAI (якщо є)
OPENAI_CV_PARSER=1              # 0=heuristic, 1=OpenAI для парсингу CV
OPENAI_CV_CLASSIFIER=1          # 0=heuristic, 1=OpenAI для класифікації
OPENAI_MATCHER=1                # 0=heuristic, 1=OpenAI для матчингу

# Оптимізація
REUSE_RUN_MAX_AGE_HOURS=4       # Пропускати Selenium якщо той самий CV < N годин тому

# Хром
CHROME_BINARY=/usr/bin/google-chrome   # Шлях до Chrome (Linux/сервер)
```

Без `OPENAI_API_KEY` — все працює, але використовує тільки heuristic методи (офлайн).

---

## 📊 Повний флоу даних від кліку до результату

```
[Браузер]
  │ Юзер відкриває http://localhost:8000
  │ → 307 redirect на /ui/
  │ → StaticFiles роздає client/index.html
  │
  │ app.js завантажується
  │ localStorage очищається
  │ UI показує Картку 1 (Account) як активну
  │
  │ Юзер натискає Register → POST /api/auth/register
  │    └─ Сервер: hash пароля, зберегти user, повернути token
  │    └─ app.js: localStorage.setItem('authToken', token)
  │    └─ setCurrentStep(1) → Картка 2 (Upload CV) стає активною
  │
  │ Юзер вибирає user_cv_1 → Upload CV → POST /api/cv/run
  │    └─ Сервер: normalize → hash → де-дуп → parse_cv (через чергу) → classify
  │    └─ Selenium: відкриває Chrome → DOU → клікає "показати ще" → збирає URL
  │    └─ upsert_jobs → job_postings (глобальний каталог)
  │    └─ JobRun + JobRunJob → знімок
  │    └─ Відповідь: {run_id, job_title, category, jobs_found}
  │    └─ app.js: setCurrentStep(2) → Картка 3 (Enrich) стає активною
  │
  │ Юзер натискає Start → runPipeline()
  │    └─ POST /api/jobs/fetch-text-all
  │         └─ Для кожної вакансії без full_text:
  │              httpx.get(source_url) → BeautifulSoup → зберегти текст
  │    └─ POST /api/jobs/enrich-all
  │         └─ Для кожної з full_text але без role_summary:
  │              OpenAI gpt-4o-mini → структуровані поля → зберегти
  │    └─ refreshJobs() → GET /api/jobs → показати список
  │    └─ refreshMatch() → GET /api/match/scores → показати рейтинг
  │
  │ Юзер клікає на вакансію в Match списку
  │    └─ GET /api/match/job/{id}/analysis
  │         └─ Перевірити job_analysis_cache
  │         └─ analyze_job(cv, job) → HTML таблиця requirements vs CV
  │    └─ Показати HTML прямо в sidebar
```

---

## 🔒 Безпека

| Аспект | Рішення |
|--------|---------|
| Паролі | PBKDF2-SHA256 з сіллю, 120к ітерацій |
| Токени | `secrets.token_hex(32)` — криптографічно стійкі |
| Timing attacks | `hmac.compare_digest()` |
| SQL injection | SQLAlchemy ORM — параметризовані запити |
| XSS | FastAPI автоматично stringify-ть output; matcher.py використовує `html.escape()` |
| CORS | Дозволено всі домени (`*`) — прийнятно для local tool |

---

## 🧩 Ключові патерни і концепції який варто запам'ятати

### 1. Dependency Injection (FastAPI)
```python
def my_endpoint(user_id: str = Depends(get_current_user_id)):
    # user_id вже є — FastAPI сам викликав get_current_user_id()
```

### 2. Context Manager для DB сесії
```python
with Session() as session:
    # тут сесія відкрита
    session.add(obj)
    session.commit()
# тут сесія автоматично закрита (навіть при помилці)
```

### 3. UUID primary keys
```python
id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
# lambda необхідна! Без неї = один UUID для всіх записів
```

### 4. De-duplication через hash
```
CV text → normalize → SHA-256 → 64 символи
Якщо hash вже є в БД → пропускаємо OpenAI → економимо гроші + час
```

### 5. Producer-Consumer черга
```
HTTP Request (producer) → queue.put((future, text))
Worker Thread (consumer) → queue.get() → parse_cv(text) → future.set_result()
HTTP Request → future.result() → отримує результат
```

### 6. Кешування
```
jobs_hash = sha256(sorted([(job_id, updated_at), ...]))
Якщо набір вакансій не змінився → job_analysis_cache ще валідний
```


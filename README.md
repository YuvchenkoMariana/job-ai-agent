# job-ai-agent — повний опис проєкту

Автоматична система пошуку роботи:
Chrome-розширення збирає вакансії з jobs.dou.ua → надсилає на Python-сервер →
сервер зберігає в базу даних → OpenAI збагачує кожну вакансію деталями.

---

## Структура проєкту

```
job-ai-agent/
│
├── chrome_extension/        ← браузерний плагін (JavaScript)
│   ├── manifest.json
│   ├── content.js
│   └── content.css
│
├── protocol/
│   └── python/
│       └── job.py           ← спільний формат даних (Python)
│
├── server/
│   └── fast_api.py          ← REST API (FastAPI)
│
├── backend/
│   ├── ai/
│   │   ├── enricher.py      ← AI збагачення вакансій (OpenAI)
│   │   └── main.py          ← тест підключення до OpenAI
│   ├── db/
│   │   ├── database.py      ← таблиці бази даних (SQLAlchemy)
│   │   └── jobs_search.db   ← SQLite файл бази даних
│   └── data/
│       ├── my_cv.md         ← твоє CV
│       ├── job_template.md  ← шаблон вакансії
│       └── jb_*.md          ← збережені вакансії
│
├── tests/
│   ├── test_api.py          ← тести сервера
│   ├── test_job_description.py ← тести протоколу
│   └── test_memory_cv.py    ← тести бази CV
│
├── conftest.py              ← налаштування pytest
├── requirements.txt         ← залежності Python
└── .env                     ← твій OpenAI ключ (не в git)
```

---

## Як запустити

### 1. Встановити залежності (один раз)
```zsh
cd /Users/mariana/PycharmProjects/job-ai-agent
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Створити .env файл (один раз)
```zsh
echo "OPENAI_API_KEY=sk-твій-ключ-тут" > .env
```

### 3. Запустити сервер
```zsh
uvicorn server.fast_api:app --reload
```
Сервер запуститься на http://localhost:8000
Документація API: http://localhost:8000/docs

### 4. Завантажити розширення в Chrome (один раз)
1. Відкрий `chrome://extensions/`
2. Увімкни **Developer mode**
3. Натисни **Load unpacked** → вибери папку `chrome_extension/`

### 5. Зібрати вакансії
1. Перейди на https://jobs.dou.ua/vacancies/?category=Python
2. Натисни **Start** у панелі розширення
3. Чекай — коли з'явиться "Synced N jobs", все збережено

### 6. Збагатити вакансії через AI
```zsh
# Одну вакансію (id=1)
curl -X POST http://localhost:8000/api/jobs/1/enrich

# Всі вакансії одразу
curl -X POST http://localhost:8000/api/jobs/enrich-all
```

### 7. Запустити тести
```zsh
pytest tests/ -v
```

---

## Файли — детальний опис

---

### `protocol/python/job.py` — формат даних

Це **угода про формат** між усіма частинами системи.
Визначає як виглядає одна вакансія і список вакансій.

```python
from __future__ import annotations
# Дозволяє використовувати TYPE_CHECKING без циклічних імпортів.
# Наприклад, JobDescription може посилатись на JobVacancy тільки для підказок типів.

import json
# Стандартна бібліотека для роботи з JSON.

from dataclasses import dataclass, field
# dataclass — автоматично генерує __init__, __repr__, __eq__ для класу.

from typing import Any, TYPE_CHECKING
# Any — тип "будь-що".
# TYPE_CHECKING — True тільки під час статичного аналізу (mypy), False під час роботи.

if TYPE_CHECKING:
    from backend.db.database import JobVacancy
# Імпорт тільки для підказок типів. Не виконується під час роботи програми.
# Це уникає циклічного імпорту (job.py ← database.py ← job.py).


@dataclass(frozen=True, slots=True)
# frozen=True — об'єкт незмінний після створення (як tuple). Не можна написати job.title = "x".
# slots=True — Python виділяє пам'ять ефективніше (немає __dict__).
class JobDescription:

    # ── Обов'язкові поля ──────────────────────────────────────────────────────
    job_title: str
    # Назва посади. Завжди заповнена плагіном.

    source_url: str
    # Посилання на вакансію. Завжди заповнена плагіном.
    # Використовується як унікальний ідентифікатор при upsert в базу.

    # ── Поле бази даних ───────────────────────────────────────────────────────
    id: int | None = None
    # Автоматично присвоюється базою при збереженні.
    # None до першого збереження.

    # ── Поля, що заповнюються AI ──────────────────────────────────────────────
    company_name: str | None = None          # Назва компанії
    company_overview: str | None = None      # Опис компанії
    location: str | None = None              # Місто / Remote / Hybrid
    work_type: str | None = None             # Full-time / Part-time / Contract
    role_summary: str | None = None          # Короткий опис ролі (1-3 речення)
    responsibilities: str | None = None      # Обов'язки
    required_quals: str | None = None        # Обов'язкові вимоги
    preferred_quals: str | None = None       # Бажані вимоги
    tools_and_methods: str | None = None     # Технології / стек
    what_success_looks: str | None = None    # Як виглядає успіх на цій ролі
    salary_min: int | None = None            # Мінімальна зарплата (число)
    salary_max: int | None = None            # Максимальна зарплата (число)
    salary_currency: str = "USD"             # Валюта. За замовчуванням USD.
    language_requirements: str | None = None # Вимоги до мов (напр. "English B2")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobDescription":
        # Створює об'єкт зі словника (наприклад, з JSON).
        # data["job_title"] — обов'язкові, KeyError якщо відсутні.
        # data.get("location") — необов'язкові, повертає None якщо відсутні.
        return cls(
            job_title=str(data["job_title"]),
            source_url=str(data["source_url"]),
            id=int(data["id"]) if data.get("id") is not None else None,
            # Якщо id є — перетворюємо на int. Якщо None — залишаємо None.
            company_name=data.get("company_name"),
            company_overview=data.get("company_overview"),
            location=data.get("location"),
            work_type=data.get("work_type"),
            role_summary=data.get("role_summary"),
            responsibilities=data.get("responsibilities"),
            required_quals=data.get("required_quals"),
            preferred_quals=data.get("preferred_quals"),
            tools_and_methods=data.get("tools_and_methods"),
            what_success_looks=data.get("what_success_looks"),
            salary_min=data.get("salary_min"),
            salary_max=data.get("salary_max"),
            salary_currency=data.get("salary_currency") or "USD",
            # or "USD" — якщо значення None або порожній рядок, беремо "USD"
            language_requirements=data.get("language_requirements"),
        )

    @classmethod
    def from_row(cls, row: "JobVacancy") -> "JobDescription":
        # Створює об'єкт зі строки бази даних (SQLAlchemy модель).
        # row.id, row.job_title — прямий доступ до колонок таблиці.
        return cls(
            id=row.id,
            job_title=row.job_title,
            source_url=row.source_url or "",
            # or "" — якщо source_url в базі NULL, повертаємо порожній рядок
            company_name=row.company_name,
            company_overview=row.company_overview,
            location=row.location,
            work_type=row.work_type,
            role_summary=row.role_summary,
            responsibilities=row.responsibilities,
            required_quals=row.required_quals,
            preferred_quals=row.preferred_quals,
            tools_and_methods=row.tools_and_methods,
            what_success_looks=row.what_success_looks,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            salary_currency=row.salary_currency or "USD",
            language_requirements=row.language_requirements,
        )

    def to_dict(self) -> dict[str, Any]:
        # Перетворює об'єкт на словник для відправки через API як JSON.
        return {
            "id": self.id,
            "job_title": self.job_title,
            "source_url": self.source_url,
            "company_name": self.company_name,
            "company_overview": self.company_overview,
            "location": self.location,
            "work_type": self.work_type,
            "role_summary": self.role_summary,
            "responsibilities": self.responsibilities,
            "required_quals": self.required_quals,
            "preferred_quals": self.preferred_quals,
            "tools_and_methods": self.tools_and_methods,
            "what_success_looks": self.what_success_looks,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "language_requirements": self.language_requirements,
        }


@dataclass(frozen=True, slots=True)
class JobDescriptionList:
    # Обгортка над списком вакансій. Вміє конвертувати в/з JSON.
    jobs: list[JobDescription]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> "JobDescriptionList":
        # Створює список об'єктів зі списку словників.
        return cls(jobs=[JobDescription.from_dict(item) for item in data])

    @classmethod
    def from_json(cls, data: str) -> "JobDescriptionList":
        # Парсить JSON рядок і перевіряє що це масив, не об'єкт.
        parsed = json.loads(data)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array of job descriptions")
        return cls.from_list(parsed)

    def to_list(self) -> list[dict[str, Any]]:
        # Перетворює кожен об'єкт на словник.
        return [job.to_dict() for job in self.jobs]

    def to_json(self) -> str:
        # Серіалізує в JSON рядок. ensure_ascii=False зберігає кирилицю як є.
        return json.dumps(self.to_list(), ensure_ascii=False)
```

---

### `backend/db/database.py` — база даних

Визначає таблиці SQLite і класи для роботи з ними.

```python
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
# create_engine — з'єднання з базою даних.
# Column, Integer, String, Text, DateTime — типи колонок.

from sqlalchemy.orm import DeclarativeBase, sessionmaker
# DeclarativeBase — базовий клас для всіх моделей таблиць.
# sessionmaker — фабрика сесій (транзакцій).

from sqlalchemy.pool import StaticPool
# StaticPool — тримає одне з'єднання весь час.
# Потрібно для in-memory SQLite: без цього кожна сесія відкриває нову (порожню) БД.

_db_url = os.getenv("DB_URL", f"sqlite:///{DB_PATH}")
# Зчитує URL бази з змінної середовища DB_URL.
# Якщо DB_URL не задана — використовує файл jobs_search.db.
# Тести задають DB_URL=sqlite:///:memory: через conftest.py.

if _db_url == "sqlite:///:memory:":
    engine = create_engine(
        _db_url,
        connect_args={"check_same_thread": False},
        # check_same_thread=False — SQLite за замовчуванням дозволяє
        # підключення тільки з одного потоку. Вимикаємо це для тестів.
        poolclass=StaticPool,
        # StaticPool — одне спільне з'єднання для всіх сесій.
        # Без цього кожна сесія бачить порожню базу.
    )
else:
    engine = create_engine(_db_url, echo=False)
    # echo=False — не виводити SQL запити в консоль.

Session = sessionmaker(bind=engine)
# Session() — відкриває транзакцію. Підтримує контекстний менеджер:
# with Session() as session: ...  — автоматично закриває при виході.
```

**Таблиця `job_vacancies`** — зберігає вакансії:
| Поле | Тип | Опис |
|------|-----|------|
| `id` | Integer PK | Автоматичний номер |
| `job_title` | String(200) | Назва посади (обов'язково) |
| `company_name` | String(200) | Назва компанії |
| `location` | String(300) | Місто / Remote |
| `work_type` | String(100) | Full-time / Remote / Hybrid |
| `role_summary` | Text | Короткий опис ролі |
| `responsibilities` | Text | Обов'язки |
| `required_quals` | Text | Обов'язкові вимоги |
| `preferred_quals` | Text | Бажані вимоги |
| `tools_and_methods` | Text | Технології |
| `what_success_looks` | Text | Критерії успіху |
| `salary_min` | Integer | Мінімальна зарплата |
| `salary_max` | Integer | Максимальна зарплата |
| `salary_currency` | String(10) | Валюта (USD за замовч.) |
| `source_url` | String(500) | Посилання (унікальний ключ) |
| `language_requirements` | String(300) | Вимоги до мови |
| `created_at` | DateTime | Коли додано |
| `updated_at` | DateTime | Коли оновлено |

**Клас `MemoryCV`** — зберігає дані CV в пам'яті (без бази).
Використовується для тестування логіки CV без реального SQLite.

```python
def init_db() -> None:
    Base.metadata.create_all(engine)
    # Створює всі таблиці у базі. Якщо таблиця вже існує — пропускає.
    # Викликається при старті сервера.
```

---

### `server/fast_api.py` — REST API сервер

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()   # Викликається один раз при старті сервера.
    yield       # Сервер працює. Код після yield виконується при зупинці.

app = FastAPI(title="Job AI Agent API", version="1.0.0", lifespan=lifespan)
# lifespan= підключає функцію старту/зупинки до додатка.

app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
# CORS — Cross-Origin Resource Sharing.
# Без цього браузер блокує запити від chrome-extension:// до localhost:8000.
# allow_origins=["*"] — дозволяє запити з будь-якого джерела.

class PluginJob(BaseModel):
    index: int = Field(ge=1)   # ge=1 — повинно бути >= 1. Pydantic відхилить index=0.
    title: str = Field(default="")
    href: str | None = Field(default=None)
# Pydantic модель — автоматично валідує вхідні JSON дані.
# Якщо тип не відповідає — FastAPI повертає 422 Unprocessable Entity.

def _clear_jobs_db() -> None:
    with Session() as session:
        session.query(JobVacancy).delete()  # DELETE FROM job_vacancies
        session.commit()                    # Підтверджує транзакцію
# Використовується тільки в тестах для очистки бази між тестами.
```

**Ендпоінти:**

```
POST /api/jobs/sync        ← плагін надсилає зібрані вакансії
GET  /api/jobs             ← читаємо список вакансій
POST /api/jobs/{id}/enrich ← збагатити одну вакансію через AI
POST /api/jobs/enrich-all  ← збагатити всі незаповнені вакансії
```

**`POST /api/jobs/sync` — логіка upsert:**
```python
existing = session.query(JobVacancy).filter_by(source_url=source_url).first()
# Шукаємо вакансію з таким самим посиланням.

if existing:
    existing.job_title = job_title    # Оновлюємо назву якщо вакансія вже є
    existing.updated_at = ...
else:
    session.add(JobVacancy(...))      # Додаємо нову якщо такого URL ще немає
```

**`POST /api/jobs/{id}/enrich` — AI збагачення:**
```python
enriched = enrich_job(source_url=job.source_url, job_title=job.job_title)
# Завантажує сторінку, питає OpenAI, отримує словник з полями.

for field, value in enriched.items():
    if hasattr(job, field) and value is not None:
        setattr(job, field, value)
# Проходить по всіх полях відповіді і записує тільки ті,
# де є значення (null не перезаписує існуючі дані).
```

---

### `backend/ai/enricher.py` — AI збагачення

```python
load_dotenv()
# Зчитує .env файл і додає змінні в os.environ.
# Після цього os.getenv("OPENAI_API_KEY") повертає твій ключ.

_PROMPT = """\
You are a job description parser...
{{  "company_name": "string or null", ... }}
"""
# {{ і }} — екранування фігурних дужок у f-string.
# Звичайні { } зарезервовані для .format(job_title=..., text=...).


def _fetch_text(url: str, max_chars: int = 8_000) -> str:
    headers = {"User-Agent": "Mozilla/5.0 ..."}
    # User-Agent — ідентифікує нас як браузер.
    # Без цього сайти можуть заблокувати запит (403 Forbidden).

    response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
    # timeout=15 — чекаємо максимум 15 секунд.
    # follow_redirects=True — автоматично переходимо по редіректах.

    response.raise_for_status()
    # Якщо статус 4xx або 5xx — кидає виключення. Якщо 200 OK — нічого не робить.

    soup = BeautifulSoup(response.text, "lxml")
    # lxml — швидкий HTML парсер.

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    # Видаляємо непотрібні елементи:
    # script — JavaScript код, style — CSS, nav/footer/header/aside — навігація.
    # Залишаємо тільки текст вакансії.

    text = soup.get_text(separator="\n", strip=True)
    # get_text() — витягує весь текст зі сторінки без HTML тегів.
    # separator="\n" — між блоками тексту ставить новий рядок.
    # strip=True — прибирає зайві пробіли.

    return text[:max_chars]
    # Обрізаємо до 8000 символів щоб не перевищити ліміт токенів OpenAI.


def enrich_job(source_url: str, job_title: str) -> dict:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # Создаємо клієнт OpenAI з ключем з .env файлу.

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        # gpt-4o-mini — швидка і дешева модель, достатня для парсингу.

        temperature=0,
        # temperature=0 — детермінований вивід (завжди однаковий результат
        # для однакового вводу). Для парсингу краще ніж випадковість.

        response_format={"type": "json_object"},
        # Гарантує що модель поверне валідний JSON, а не текст з JSON всередині.

        messages=[{"role": "user", "content": _PROMPT.format(...)}],
    )

    return json.loads(response.choices[0].message.content)
    # response.choices[0] — перший (і єдиний) варіант відповіді.
    # .message.content — текст відповіді (вже валідний JSON рядок).
    # json.loads() — перетворює рядок на Python словник.
```

---

### `backend/ai/main.py` — тест підключення до OpenAI

Простий скрипт для перевірки що API ключ працює.

```python
load_dotenv()
# Завантажує OPENAI_API_KEY з .env файлу.

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY is not set.")
    return 1
# Перевіряємо наявність ключа перед запитом.
# return 1 — код виходу 1 означає помилку (0 = успіх).

except RateLimitError as error:
    body_code = (getattr(error, "body", {}) or {}).get("error", {}).get("code")
    # getattr(error, "body", {}) — безпечний доступ до атрибута body.
    # Якщо body відсутній — повертає {}.
    # or {} — якщо body це None, теж беремо {}.
    if code == "insufficient_quota":
        print("Error: insufficient quota.")
    # insufficient_quota — закінчились гроші на рахунку OpenAI.
```

Запуск:
```zsh
python backend/ai/main.py
```

---

### `chrome_extension/` — браузерний плагін

#### `manifest.json` — конфігурація розширення

```json
{
  "manifest_version": 3,
  // Версія формату маніфесту. 3 — актуальна версія Chrome.

  "permissions": ["activeTab", "scripting", "storage"],
  // activeTab — доступ до поточної вкладки.
  // scripting — дозвіл запускати скрипти на сторінці.
  // storage — дозвіл зберігати дані (chrome.storage.local).

  "host_permissions": [
    "https://jobs.dou.ua/*",
    // Дозволяє запускати content.js на цьому сайті.
    "http://localhost:8000/*"
    // Дозволяє fetch() запити до нашого сервера.
    // Без цього браузер заблокує запит з помилкою CORS.
  ]
}
```

#### `content.js` — головний скрипт (вставляється в сторінку)

```javascript
const TAB_ID = getTabId();
// Унікальний ID поточної вкладки. Генерується один раз і зберігається
// в sessionStorage (живе до закриття вкладки).
// Потрібен щоб різні вкладки не перезаписували стан одна одної.

intervalId = setInterval(openMoreJobs, 5000);
// Запускає openMoreJobs() кожні 5000 мілісекунд (5 секунд).
// Повертає ID таймера — зберігаємо щоб потім зупинити через clearInterval(intervalId).

function openMoreJobs() {
  const xpath = '//*[@id="vacancyListId"]/div/a';
  const element = getElementByXPath(xpath);
  // XPath — мова для пошуку елементів в HTML документі.
  // //* — будь-який елемент. [@id="vacancyListId"] — з таким id.
  // /div/a — всередині div шукаємо посилання <a>.

  const isHidden = element.style.display === 'none'
    || window.getComputedStyle(element).display === 'none';
  // Перевіряємо чи кнопка прихована.
  // style.display — інлайн стиль.
  // getComputedStyle — фінальний стиль після всіх CSS правил.

  if (isHidden) {
    syncJobsToApi();   // Всі вакансії завантажені — відправляємо на сервер
    stopNavigation();
    return;
  }

  element.click();    // Клікаємо "Показати ще"
  clickCount++;
  saveState();        // Зберігаємо прогрес після кожного кліку
}

async function syncJobsToApi() {
  const jobs = getAllJobs();
  // Збирає всі <li> з контейнера вакансій на сторінці.

  const res = await fetch("http://localhost:8000/api/jobs/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
    // JSON.stringify — перетворює JavaScript масив на рядок JSON.
  });

  if (!res.ok) throw new Error(`Sync failed: ${res.status}`);
  // res.ok — true якщо статус 200-299, false якщо 4xx/5xx.
}

function saveState() {
  chrome.storage.local.set({ [storageKey]: { isRunning, clickCount, timestamp } });
  // chrome.storage.local — сховище розширення. Зберігається між перезавантаженнями.
  // [storageKey] — обчислюваний ключ (динамічна назва властивості об'єкта).
}

function loadState() {
  if (now - savedTime > fiveMinutes) {
    chrome.storage.local.remove(storageKey);
    return;
  }
  // Якщо стан старіший 5 хвилин — ігноруємо його.
  // Це запобігає "зависанню" розширення після довгої паузи.

  if (savedState.isRunning) {
    setTimeout(() => { startNavigation(); }, 5000);
    // Відновлює роботу через 5 секунд після перезавантаження сторінки.
    // setTimeout — однократний таймер (на відміну від setInterval).
  }
}
```

---

### `conftest.py` — налаштування тестів

```python
os.environ.setdefault("DB_URL", "sqlite:///:memory:")
# setdefault — встановлює змінну ТІЛЬКИ якщо вона ще не задана.
# sqlite:///:memory: — SQLite база в оперативній пам'яті.
# Зникає після завершення тестів. Не торкається jobs_search.db.
# Цей рядок виконується ДО будь-яких імпортів тестів,
# тому database.py читає вже змінений DB_URL.

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# __file__ — шлях до conftest.py (/project/conftest.py).
# os.path.abspath — абсолютний шлях.
# os.path.dirname — папка файлу (/project/).
# sys.path.insert(0, ...) — додає папку на початок списку де Python шукає модулі.
# Без цього import server.fast_api не знайде модуль server.
```

---

### `tests/test_api.py` — тести сервера

```python
@pytest.fixture(autouse=True)
def clear_store():
    # autouse=True — цей fixture застосовується до КОЖНОГО тесту автоматично.
    init_db()        # Створює таблиці в in-memory базі
    _clear_jobs_db() # Очищає таблицю перед тестом
    yield            # Тут виконується тест
    _clear_jobs_db() # Очищає після тесту
    # yield розділяє "setup" і "teardown" частини fixture.

client = TestClient(app)
# TestClient — імітує HTTP запити без реального запуску сервера.
# Швидко, без мережі, без портів.
```

---

### `requirements.txt` — залежності

```
fastapi          # Веб-фреймворк для REST API
uvicorn          # ASGI сервер що запускає FastAPI
pydantic         # Валідація даних (використовується FastAPI)
httpx            # HTTP клієнт (для завантаження сторінок і TestClient)
sqlalchemy       # ORM для роботи з базою даних
openai           # Клієнт OpenAI API
python-dotenv    # Завантаження .env файлів
selenium         # Автоматизація браузера (Selenium scraper)
webdriver-manager # Автоматичне завантаження ChromeDriver
beautifulsoup4   # Парсинг HTML (витягування тексту з вакансій)
lxml             # Швидкий HTML/XML парсер (використовується BeautifulSoup)
pytest           # Фреймворк для тестів
pytest-asyncio   # Підтримка async тестів
```

---

## Повний потік даних

```
1. jobs.dou.ua
   ↓ (Chrome завантажує content.js)

2. Розширення клікає "Показати ще" кожні 5 секунд

3. Коли кнопки більше немає → getAllJobs() збирає всі <li>:
   [{index:1, title:"Python Dev", href:"https://..."}, ...]

4. syncJobsToApi() → POST /api/jobs/sync
   Сервер: для кожного href — якщо є в базі → update, якщо немає → insert

5. База даних: job_vacancies
   id=1, job_title="Python Dev", source_url="...", company_name=NULL, ...

6. POST /api/jobs/enrich-all
   Для кожної вакансії де role_summary IS NULL:
     a. _fetch_text() завантажує сторінку вакансії
     b. BeautifulSoup витягує чистий текст
     c. OpenAI gpt-4o-mini заповнює всі поля
     d. Зберігаємо в базу (тільки не-null значення)

7. GET /api/jobs → повертає повністю заповнені вакансії:
   {id:1, job_title:"Python Dev", company_name:"EPAM", location:"Remote", ...}
```


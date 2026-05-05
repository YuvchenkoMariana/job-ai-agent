# Пояснення проєкту job-ai-agent від А до Я

---

## Що це взагалі за проєкт?

Це система з трьох частин, які працюють разом:

```
[jobs.dou.ua]  →  [Chrome розширення]  →  [Python сервер]  →  [твій код / AI агент]
   сайт з           збирає вакансії        зберігає і          читає готовий
  вакансіями        зі сторінки            віддає через API     список вакансій
```

---

## Частина 1 — `protocol/python/job.py` (Протокол даних)

### Що це?
Це **угода про формат даних** між усіма частинами системи.
Визначає як виглядає одна вакансія і список вакансій.

### Що всередині?

#### `JobDescription` — одна вакансія
```python
@dataclass(frozen=True, slots=True)
class JobDescription:
    id: int      # номер вакансії (1, 2, 3...)
    title: str   # назва посади: "Python Engineer"
    href: str    # посилання: "https://jobs.dou.ua/..."
```

- `frozen=True` — об'єкт незмінний після створення (як tuple)
- `slots=True` — економія пам'яті

#### `JobDescriptionList` — список вакансій
Обгортка над списком `JobDescription`. Вміє:
- `from_json(string)` — розпарсити JSON рядок у список об'єктів
- `to_json()` — перетворити список об'єктів у JSON рядок
- `from_list(list)` — зробити список об'єктів зі списку словників
- `to_list()` — зробити список словників зі списку об'єктів

### Навіщо це потрібно?
Щоб і сервер, і тести використовували **одні й ті ж правила** для даних.
Якщо змінити формат — змінюєш тільки тут, все інше адаптується.

---

## Частина 2 — `chrome_extension/` (Chrome розширення)

### Що це?
Маленька програма що вбудовується в браузер Chrome і запускається
автоматично коли відкриваєш `https://jobs.dou.ua/`.

### Файли розширення

| Файл | Що робить |
|------|-----------|
| `manifest.json` | Конфіг розширення: назва, дозволи, які сайти |
| `content.js` | Головний код що інжектується в сторінку |
| `content.css` | Стилі для панелі керування |
| `popup.html` | HTML попапу (іконка в браузері) |
| `popup.js` | Логіка попапу |
| `icon*.svg` | Іконки розширення |

### `manifest.json` — навіщо?

```json
{
  "permissions": ["activeTab", "scripting", "storage"],
  "host_permissions": [
    "https://jobs.dou.ua/*",
    "http://localhost:8000/*"   ← дозвіл звертатись до нашого сервера
  ]
}
```

- `storage` — дозвіл зберігати стан (чи запущено, скільки кліків)
- `host_permissions` — з яких сайтів дозволено робити запити
- Без `http://localhost:8000/*` розширення не зможе відправити вакансії на сервер

### `content.js` — як працює?

#### 1. Панель керування
Коли відкриваєш jobs.dou.ua — автоматично з'являється панель у куті:
```
[Dou Navigator]
Status: Stopped
[Start] [Stop]
Clicks: 0
```

#### 2. `startNavigation()` — що робить Start
- Встановлює `isRunning = true`
- Запускає `setInterval(openMoreJobs, 5000)` — кожні 5 секунд викликає `openMoreJobs`

#### 3. `openMoreJobs()` — серце розширення
Кожні 5 секунд:
1. Шукає кнопку "Показати ще" на сторінці по XPath: `//*[@id="vacancyListId"]/div/a`
2. Якщо знайшла — клікає на неї (завантажує ще вакансії)
3. Прокручує сторінку вниз щоб підвантажились нові елементи
4. Якщо кнопка прихована (всі вакансії завантажені) — **зупиняється і відправляє дані на сервер**
5. Якщо кнопка взагалі не знайдена — теж зупиняється і відправляє

#### 4. `getAllJobs()` — збирає вакансії зі сторінки
Знаходить елемент `//*[@id="vacancyListId"]/ul` і збирає з нього всі `<li>`:
```javascript
{
  index: 1,           // порядковий номер
  title: "Python Dev", // текст посилання
  href: "https://..."  // посилання на вакансію
}
```

#### 5. `syncJobsToApi()` — відправляє на сервер
```javascript
fetch("http://localhost:8000/api/jobs/sync", {
  method: "POST",
  body: JSON.stringify(jobs)   // масив вакансій
})
```
Після успішного відправлення панель показує `"Synced N jobs"`.

#### 6. Збереження стану (`saveState` / `loadState`)
Якщо сторінка перезавантажилась — розширення пам'ятає чи було запущено
і автоматично відновлює роботу через 5 секунд.
Стан зберігається в `chrome.storage.local` і живе 5 хвилин.

---

## Частина 3 — `server/` (Python API сервер)

### Що це?
Веб-сервер написаний на **FastAPI** — отримує вакансії від розширення
і віддає їх будь-кому через HTTP.

### Файли

| Файл | Що робить |
|------|-----------|
| `server/main.py` | Головний файл сервера, всі ендпоінти |
| `server/requirements.txt` | Список залежностей (бібліотек) |
| `server/tests/test_api.py` | Автоматичні тести |

### `server/main.py` — як влаштований?

#### Сховище (in-memory store)
```python
_job_store: list[JobDescription] = []
```
Простий Python список. Живе поки сервер запущений.
Після перезапуску — порожній. (Можна замінити на базу даних пізніше)

#### `POST /api/jobs/sync` — приймає вакансії від розширення

**Що приходить від розширення:**
```json
[
  {"index": 1, "title": "Python Dev", "href": "https://jobs.dou.ua/1"},
  {"index": 2, "title": "Go Dev",     "href": "https://jobs.dou.ua/2"}
]
```

**Що відбувається всередині:**
1. Валідація через `PluginJob` модель (Pydantic перевіряє типи)
2. Конвертація: `index` → `id` (формат протоколу `job.py`)
3. Обрізка пробілів у назвах і посиланнях
4. Фільтрація порожніх вакансій
5. Сортування за `id`
6. Збереження в `_job_store` (попередні дані заміняються)

**Що повертає:**
```json
{"count": 2}
```

#### `GET /api/jobs` — віддає список вакансій

**Що повертає:**
```json
[
  {"id": 1, "title": "Python Dev", "href": "https://jobs.dou.ua/1"},
  {"id": 2, "title": "Go Dev",     "href": "https://jobs.dou.ua/2"}
]
```

Використовує `JobDescriptionList.to_list()` з протоколу — завжди єдиний формат.

#### CORS Middleware
```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
```
Без цього браузер блокував би запити від розширення до сервера
(захист від крос-доменних запитів).

### `server/tests/test_api.py` — навіщо тести?

Автоматично перевіряють що сервер працює правильно.
Використовують `TestClient` — імітує HTTP запити без реального запуску сервера.

Фікстура `clear_store` — очищає сховище перед кожним тестом щоб вони не впливали один на одного.

Що перевіряється:
- `GET /api/jobs` повертає `[]` якщо нічого немає
- Після `POST /api/jobs/sync` дані доступні через `GET`
- Дані відсортовані за `id`
- Пусті вакансії фільтруються
- Пробіли обрізаються
- Порожній список → помилка 422
- `index` з розширення стає `id` у відповіді

---

## Повний потік даних (від кліку до результату)

```
1. Ти відкриваєш https://jobs.dou.ua/vacancies/?category=Python

2. Chrome завантажує content.js → з'являється панель "Dou Navigator"

3. Ти натискаєш [Start]

4. Кожні 5 секунд: розширення клікає "Показати ще"
   → нові вакансії підвантажуються на сторінку

5. Коли кнопки більше немає → розширення зупиняється

6. getAllJobs() збирає всі <li> зі сторінки:
   [{index:1, title:"...", href:"..."}, ...]

7. syncJobsToApi() відправляє POST http://localhost:8000/api/jobs/sync
   з масивом вакансій

8. Сервер:
   - валідує дані
   - конвертує index → id
   - зберігає в _job_store

9. Панель показує "Synced 47 jobs" ✅

10. Твій код / AI агент викликає GET http://localhost:8000/api/jobs
    → отримує список вакансій у форматі протоколу
```

---

## Як запустити

### Перший раз (встановлення)
```zsh
cd /Users/mariana/PycharmProjects/job-ai-agent
source .venv/bin/activate
pip install -r requirements.txt
```

### Щоразу (запуск сервера)
```zsh
cd /Users/mariana/PycharmProjects/job-ai-agent
source .venv/bin/activate
uvicorn server.fast_api:app --reload
```

### Завантажити розширення в Chrome (один раз)
1. `chrome://extensions/`
2. Увімкни **Developer mode**
3. **Load unpacked** → вибери папку `chrome_extension/`

### Запустити тести
```zsh
pytest server/tests/test_api.py -v
```

---

## Структура файлів

```
job-ai-agent/
│
├── protocol/
│   └── python/
│       ├── job.py                       ← формат даних (JobDescription, JobDescriptionList)
│       └── tests/
│           └── test_job_description.py  ← тести протоколу
│
├── chrome_extension/
│   ├── manifest.json                    ← конфіг розширення + дозволи
│   ├── content.js                       ← логіка скролінгу + відправка на API
│   ├── content.css                      ← стилі панелі
│   ├── popup.html / popup.js            ← попап іконки
│   └── icon*.svg                        ← іконки
│
├── server/
│   ├── fast_api.py                      ← FastAPI сервер (GET/POST ендпоінти)
│   └── tests/
│       └── test_api.py                  ← тести сервера
│
├── job_agent/                           ← AI агент, скрапер, БД
│   ├── ai/
│   │   └── main.py                      ← OpenAI клієнт
│   ├── db/
│   │   ├── database.py                  ← SQLAlchemy моделі (MyCv, JobVacancy, MemoryCV)
│   │   └── jobs_search.db               ← SQLite база даних
│   ├── scraper/
│   │   └── scraper.py                   ← Selenium скрапер (djinni.co)
│   ├── data/
│   │   ├── my_cv.md                     ← твоє CV
│   │   ├── job_template.md              ← шаблон вакансії
│   │   └── jb_*.md                      ← зібрані вакансії
│   └── tests/
│       └── test_memory_cv.py            ← тести MemoryCV
│
├── requirements.txt                     ← всі залежності
├── pyproject.toml                       ← конфіг pytest
└── EXPLANATION.md                       ← цей файл 😊
```

---

## Часті запитання

**Q: Чому `GET /api/jobs` повертає `[]`?**
A: Розширення ще не відправило дані. Спочатку треба запустити Start на jobs.dou.ua і дочекатись "Synced N jobs".

**Q: Дані зникли після перезапуску сервера?**
A: Так — зберігаються тільки в пам'яті. Після перезапуску потрібно знову запустити розширення.

**Q: Як подивитись API у браузері?**
A: Відкрий `http://localhost:8000/docs` — там інтерактивна документація.

**Q: Де змінити інтервал між кліками?**
A: `content.js`, рядок `setInterval(openMoreJobs, 5000)` — замість 5000 вкажи потрібну кількість мілісекунд.


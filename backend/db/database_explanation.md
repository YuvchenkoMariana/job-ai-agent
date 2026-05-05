# Пояснення database.py — від А до Я

---

## 📦 Імпорти

```python
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime
)
```
Імпортуємо з бібліотеки SQLAlchemy:
- `create_engine` — створює з'єднання з базою даних
- `Column` — позначає, що поле є колонкою в таблиці
- `Integer, String, Text, DateTime` — типи даних для колонок (як `int`, `varchar`, `text`, `datetime` в SQL)

```python
from sqlalchemy.orm import DeclarativeBase, sessionmaker
```
- `DeclarativeBase` — базовий клас, від якого наслідуються всі наші моделі (таблиці)
- `sessionmaker` — фабрика для створення **сесій** (сесія = одне з'єднання з БД для читання/запису)

```python
from datetime import datetime, timezone
```
Потрібно для автоматичного запису часу створення/оновлення запису.

```python
import os
```
Для роботи з шляхами до файлів на диску.

---

## ⚙️ Налаштування двигуна (Engine)

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```
- `__file__` — це шлях до поточного файлу (`database.py`)
- `os.path.abspath(...)` — робить його абсолютним (повним)
- `os.path.dirname(...)` — бере тільки папку, без імені файлу

→ Результат: `/Users/mariana/PycharmProjects/Jobs_search/db`

```python
DB_PATH = os.path.join(BASE_DIR, "jobs_search.db")
```
Склеює папку і назву файлу БД.  
→ Результат: `/Users/mariana/PycharmProjects/Jobs_search/db/jobs_search.db`

```python
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
```
Створює **двигун** — об'єкт, який знає як підключитись до БД.  
- `sqlite:///` — вказує, що використовуємо SQLite (файлова БД, не сервер)
- `echo=False` — не виводити кожен SQL-запит у консоль (постав `True` щоб бачити SQL)

```python
Session = sessionmaker(bind=engine)
```
Створює **клас сесії**, прив'язаний до нашого двигуна.  
Потім щоразу коли треба щось зробити з БД — пишемо `session = Session()`.

---

## 🏗️ Base — базовий клас для таблиць

```python
class Base(DeclarativeBase):
    pass
```
Це порожній базовий клас. Всі наші моделі (таблиці) будуть від нього наслідуватись.  
SQLAlchemy через нього відстежує всі таблиці, щоб потім створити їх в БД.

---

## 🗂️ Таблиця 1: `MyCv`

```python
class MyCv(Base):
```
Оголошуємо клас-модель. Один об'єкт цього класу = один рядок в таблиці.

```python
    __tablename__ = "my_cv"
```
Назва таблиці в SQLite-файлі. Саме так вона буде називатись в БД.

```python
    id = Column(Integer, primary_key=True, autoincrement=True)
```
- `Column(...)` — це колонка в таблиці
- `Integer` — тип: ціле число
- `primary_key=True` — це головний ключ (унікальний ідентифікатор кожного рядка)
- `autoincrement=True` — число збільшується автоматично (1, 2, 3…), не треба вказувати вручну

```python
    job_title = Column(String(200), nullable=False)
```
- `String(200)` — текст до 200 символів (як `VARCHAR(200)` в SQL)
- `nullable=False` — **обов'язкове** поле, без нього запис не збережеться

```python
    full_name    = Column(String(200), nullable=True)
    email        = Column(String(200), nullable=True)
    phone        = Column(String(50),  nullable=True)
    location     = Column(String(300), nullable=True)
    github_url   = Column(String(300), nullable=True)
    linkedin_url = Column(String(300), nullable=True)
```
Всі контактні поля. `nullable=True` — **необов'язкові**, можна залишити порожніми.

```python
    profile_summary     = Column(Text, nullable=True)
    programming_skills  = Column(Text, nullable=True)
    tools_and_tech      = Column(Text, nullable=True)
    other_skills        = Column(Text, nullable=True)
    projects            = Column(Text, nullable=True)
    education           = Column(Text, nullable=True)
    career_objective    = Column(Text, nullable=True)
    additional_info     = Column(Text, nullable=True)
```
Великі текстові блоки. `Text` на відміну від `String` — **необмежений** за довжиною текст.

```python
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```
Час створення запису.  
- `default=lambda: ...` — функція, що викликається **автоматично** при кожному новому записі
- `datetime.now(timezone.utc)` — поточний час в UTC

```python
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))
```
Час останнього оновлення.  
- `onupdate=...` — автоматично оновлюється щоразу, коли запис змінюється

```python
    def __repr__(self) -> str:
        return f"<MyCv id={self.id} job_title='{self.job_title}' name='{self.full_name}'>"
```
Магічний метод Python — визначає, що виводиться коли ти робиш `print(cv_object)`.  
Замість `<__main__.MyCv object at 0x...>` побачиш `<MyCv id=1 job_title='Python Developer'>`.

---

## 🗂️ Таблиця 2: `JobVacancy`

```python
class JobVacancy(Base):
    __tablename__ = "job_vacancies"
```
Аналогічно до `MyCv` — клас-модель, один об'єкт = один рядок в таблиці `job_vacancies`.

```python
    id = Column(Integer, primary_key=True, autoincrement=True)
```
Те саме що і в `MyCv` — автоматичний унікальний ID.

```python
    job_title        = Column(String(200), nullable=False)  # назва посади — обов'язкова
    company_name     = Column(String(200), nullable=True)   # компанія
    company_overview = Column(Text,        nullable=True)   # опис компанії
```
Основна ідентифікація вакансії.

```python
    location  = Column(String(300), nullable=True)  # місто / ремоут
    work_type = Column(String(100), nullable=True)  # Full-time / Remote / Hybrid
```
Де і як проходить робота.

```python
    role_summary       = Column(Text, nullable=True)  # загальний опис ролі
    responsibilities   = Column(Text, nullable=True)  # обов'язки
    required_quals     = Column(Text, nullable=True)  # обов'язкові вимоги
    preferred_quals    = Column(Text, nullable=True)  # бажані вимоги
    tools_and_methods  = Column(Text, nullable=True)  # стек технологій
    what_success_looks = Column(Text, nullable=True)  # як виглядає успіх у цій ролі
```
Основні блоки опису вакансії.

```python
    salary_min      = Column(Integer,    nullable=True)              # нижня межа зарплати
    salary_max      = Column(Integer,    nullable=True)              # верхня межа зарплати
    salary_currency = Column(String(10), nullable=True, default="USD")  # валюта, за замовч. USD
    benefits        = Column(Text,       nullable=True)              # бенефіти
```
Компенсаційний пакет. `default="USD"` — якщо не вказати валюту, підставляється USD автоматично.

```python
    how_to_apply          = Column(Text,        nullable=True)  # як подати заявку
    source_url            = Column(String(500), nullable=True)  # посилання на вакансію
    language_requirements = Column(String(300), nullable=True)  # вимоги до мов
```
Інформація для подачі заявки та джерело вакансії.

```python
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))
```
Мета-поля часу — ідентичні до `MyCv`.

```python
    def __repr__(self) -> str:
        return f"<JobVacancy id={self.id} title='{self.job_title}' company='{self.company_name}'>"
```
Зручний вивід об'єкта при `print(vacancy_object)`.

---

## 🔧 Функція `init_db()`

```python
def init_db() -> None:
    Base.metadata.create_all(engine)
    print(f"Database ready at: {DB_PATH}")
```
- `Base.metadata` — містить інформацію про всі класи, що наслідують `Base`
- `create_all(engine)` — перевіряє кожну таблицю: якщо не існує — **створює**, якщо є — **пропускає**

→ Безпечно викликати кілька разів — нічого не пошкодить і не перезапише.

---

## 🌱 Функція `seed_cv()`

```python
def seed_cv() -> None:
    session = Session()   # відкриваємо з'єднання з БД
```
`Session()` — створює новий об'єкт сесії (одне активне з'єднання з БД).

```python
    try:
        if session.query(MyCv).first():
            print("CV record already exists — skipping seed.")
            return
```
- `session.query(MyCv)` — виконує `SELECT * FROM my_cv`
- `.first()` — повертає перший рядок або `None` якщо таблиця порожня
- Якщо запис вже є — **виходимо**, щоб не дублювати дані

```python
        cv = MyCv(
            job_title = "Python Developer (Entry Level)",
            full_name = "Ivan Petrenko",
            ...
        )
```
Створюємо **об'єкт в пам'яті** — в цей момент в БД ще **нічого не записано**.

```python
        session.add(cv)
```
Говоримо сесії: "відстежуй цей об'єкт, підготуй його до запису".

```python
        session.commit()
```
**Підтверджує транзакцію** — тільки тут дані фізично записуються у файл БД.  
Виконується SQL: `INSERT INTO my_cv (job_title, full_name, ...) VALUES (...)`

```python
    finally:
        session.close()
```
`finally` — виконується **завжди**, навіть якщо була помилка.  
Закриває з'єднання з БД — важливо, щоб не було витоків пам'яті.

---

## ▶️ Точка входу

```python
if __name__ == "__main__":
    init_db()
    seed_cv()
```
- `if __name__ == "__main__"` — цей блок виконується **тільки** коли запускаєш файл напряму (`python database.py`)
- Якщо цей файл **імпортується** в іншому файлі (`from db.database import MyCv`) — блок **не виконується**

→ Тобто `init_db()` і `seed_cv()` запустяться тільки при прямому запуску, не при імпорті.

---

## 🔄 Загальна схема роботи

```
python database.py
       │
       ├─ init_db()
       │       └─ Base.metadata.create_all(engine)
       │               └─ CREATE TABLE IF NOT EXISTS my_cv (...)
       │               └─ CREATE TABLE IF NOT EXISTS job_vacancies (...)
       │
       └─ seed_cv()
               └─ session = Session()         # відкрити з'єднання
               └─ query(MyCv).first()         # перевірити чи є дані
               └─ cv = MyCv(...)              # створити об'єкт в пам'яті
               └─ session.add(cv)             # додати до черги
               └─ session.commit()            # записати в БД
               └─ session.close()             # закрити з'єднання
```


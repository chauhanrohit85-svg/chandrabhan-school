# 🏫 Chandrabhan Singh Public School — Management Ecosystem

A production-ready, zero-licensing-cost school management system built with **Python (Flask)** + **SQLite**.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Copy & Configure Environment
```bash
copy .env.example .env
# Edit .env to set SECRET_KEY and other settings
```

### 3. Initialize Database & Seed Data
```bash
python migrations/init_db.py
```

### 4. Run the Server
```bash
python run.py
```

Open: [http://localhost:5000](http://localhost:5000)

---

## 🔑 First-Run Credentials

There are **no default passwords**. The first time the app starts against an
empty database it creates `director`, `principal` and `teacher1`–`5`, then either:

- uses `BOOTSTRAP_DIRECTOR_PASSWORD` / `BOOTSTRAP_ADMIN_PASSWORD` /
  `BOOTSTRAP_TEACHER_PASSWORD` if you set them, or
- generates strong random passwords and **prints them once** to the startup log.

Copy them from the log on first deploy — they are stored only as bcrypt hashes
and cannot be recovered afterwards. The Principal can reset any password from
Admin → Teachers.

---

## 📺 TV Display (Smart TV Kiosk)

TV pages show student names, roll numbers and attendance, so they require a login.

1. Admin → **Teachers** → create a user with role `tv` and an assigned class
2. On the classroom Smart TV browser, sign in as that user with **Keep me signed in**
3. It lands on its class view and stays signed in across restarts
4. Press **Fullscreen** or F11

A `tv` account can only open its own class. Staff accounts can open any class.

TV view auto-refreshes every **5 minutes** and shows:
- Real-time attendance KPIs
- 5-Pillar radar chart (last 4 weeks)
- Active student alerts
- Live clock

---

## 📶 Offline-First (SIM Card Resilience)

Teacher forms **auto-save to localStorage every 3 seconds**.  
When Wi-Fi / SIM drops:
- Data is preserved locally in the browser
- `sync.js` polls `/api/health` every 30 seconds
- On reconnect, all pending data auto-syncs to server

---

## 🗂 Module Overview

| Module | URL Prefix | Description |
|--------|-----------|-------------|
| Auth   | `/auth`   | Login, logout |
| Admin  | `/admin`  | Dashboard, reports, alerts, user/student management |
| Teacher| `/teacher`| Daily log, attendance, pillar scores |
| TV     | `/tv`     | Smart TV kiosk display |
| API    | `/api`    | Offline sync endpoints |

---

## 📊 5 Pillar Tracking

| Pillar | Icon | Description |
|--------|------|-------------|
| English Speaking | 🗣️ | Oral communication skills |
| Mathematics | 🔢 | Numeracy and problem solving |
| Reasoning | 🧠 | Critical thinking |
| Reading | 📖 | Comprehension and fluency |
| Writing | ✍️ | Written expression |

Each pillar is scored weekly:
- **Qualitative**: 1 (Needs Work) → 5 (Excellent) via star rating
- **Quantitative**: 0–100% score

---

## 🚨 Auto-Alert System

Alerts are auto-generated when:
1. A student's average pillar score falls below **2.0/5.0** over 4 weeks
2. A student has **3+ consecutive absences**

Admins can resolve alerts from the Alerts dashboard.

---

## 🏗 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, Flask 3.0 |
| Database | SQLite (WAL mode) / PostgreSQL (Render) |
| Auth | Flask-Login + bcrypt |
| Frontend | Semantic HTML5, Tailwind CSS CDN, Vanilla JS |
| Charts | Chart.js 4.4 (CDN) |
| Deployment | Gunicorn + Render / Local PC |

---

## 🌐 Cloud Deployment (Render)

1. Push to GitHub
2. Connect repo to [Render](https://render.com)
3. Set environment variables in the Render dashboard:
   - `DATABASE_URL` = your Neon PostgreSQL connection string (**required**)
   - `SECRET_KEY` = a long random string (**required**)
   - `FLASK_ENV` = `production`
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn run:app`

Tables are created and master accounts seeded automatically at startup, so there
is no separate migration step.

### Storage guarantees

The app **will not start** if `DATABASE_URL` is missing, if it is not a
PostgreSQL URL, if the PostgreSQL driver cannot be imported, or if the database
is unreachable after 5 retries. This is deliberate: Render's disk is ephemeral,
so a silent fall back to SQLite means every student record entered since the
last deploy is erased on the next restart. A failed deploy that says why is
better than a portal that quietly loses data.

Python is pinned in `.python-version`. `psycopg2-binary` publishes no wheels for
Python 3.13, and an unimportable driver was the original cause of production
falling back to SQLite.

To confirm storage at any time: Director → **Storage Diagnostics**, or
`GET /health/db` which returns `{"engine": "postgresql", "permanent": true}`.

---

## 🧪 Running Tests

```bash
pytest tests/ -v --tb=short
```

Expected: **88 tests, all green**

---

## 📁 Project Structure

```
chandrabhan-school/
├── app/
│   ├── __init__.py       # App factory
│   ├── models.py         # 7 ORM models
│   ├── config.py         # Dev/Prod/Test configs
│   ├── extensions.py     # db, login_manager
│   ├── auth/             # Login/logout routes
│   ├── admin/            # Admin dashboard + reports
│   ├── teacher/          # Teacher portal
│   ├── tv/               # Smart TV kiosk
│   ├── api/              # Offline sync API
│   ├── static/           # CSS, JS
│   └── templates/        # All HTML templates
├── migrations/
│   └── init_db.py        # DB setup + seed
├── tests/                # 23+ pytest tests
├── run.py                # Entry point
├── requirements.txt
└── Procfile              # Render deployment
```

---

*Built by the D-O-E Framework for Chandrabhan Singh Public School · 2025-26*

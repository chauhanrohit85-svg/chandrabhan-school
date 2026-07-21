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

## 🔑 Default Credentials

| Role     | Username       | Password    |
|----------|----------------|-------------|
| Admin    | `principal`    | `admin123`  |
| Teacher  | `teacher1`–`5` | `teacher123`|

> ⚠️ Change all passwords after first login in production!

---

## 📺 TV Display (Smart TV Kiosk)

1. Open Admin → **TV Kiosk Views**
2. Copy the class URL
3. Open it on the classroom Smart TV browser
4. Press **Fullscreen** button or F11

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
3. Set environment variables in Render dashboard:
   - `SECRET_KEY` = (random string)
   - `FLASK_ENV` = production
4. Build command: `pip install -r requirements.txt && python migrations/init_db.py`
5. Start command: `gunicorn run:app`

---

## 🧪 Running Tests

```bash
pytest tests/ -v --tb=short
```

Expected: **~23 tests, all green**

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

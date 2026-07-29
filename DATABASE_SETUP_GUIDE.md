# 🌐 Permanent Cloud Database Setup Guide (Prevent Ephemeral Data Loss)

Render's free tier web services use **ephemeral container disks**, which reset when the server sleeps or restarts. To guarantee that student records, teacher accounts, daily logs, and 5-pillar evaluations survive server restarts **permanently for $0/month**, attach a free Cloud PostgreSQL database using the instructions below.

---

## ⚡ Option A: Neon.tech PostgreSQL (Recommended — $0/month)

[Neon.tech](https://neon.tech) provides a serverless PostgreSQL database with a generous **100% free tier** (500 MB storage, instant branching, 0 cold-start delays).

### Step-by-Step Setup:
1. Go to **[https://neon.tech](https://neon.tech)** and sign up for a free account.
2. Click **Create Project**, name your project `chandrabhan-school-db`, and select PostgreSQL version 16+.
3. On your project dashboard, locate the **Connection Details** box.
4. Copy the full connection string (it looks like `postgres://user:password@ep-xyz.neon.tech/neondb?sslmode=require`).
5. Go to your **Render Dashboard** → Select your `chandrabhan-school` web service.
6. Click **Environment** in the left sidebar → Click **Add Environment Variable**.
7. Enter:
   - **Key**: `DATABASE_URL`
   - **Value**: *(Paste your Neon connection string here)*
8. Click **Save Changes**.

> [!NOTE]
> The Chandrabhan Singh Public School backend automatically converts `postgres://` URLs to `postgresql://` and runs `db.create_all()` on boot, so your database will immediately be initialized without any extra commands!

---

## 🟢 Option B: Supabase PostgreSQL ($0/month)

[Supabase](https://supabase.com) offers free hosted PostgreSQL databases.

### Step-by-Step Setup:
1. Go to **[https://supabase.com](https://supabase.com)** and sign up for a free tier account.
2. Click **New Project**, set a password, and create your database.
3. Go to **Project Settings** → **Database** → **Connection String** → Select **URI**.
4. Copy the URI string (e.g., `postgresql://postgres:[YOUR-PASSWORD]@db.xyz.supabase.co:5432/postgres`).
5. Open **Render Dashboard** → Select your `chandrabhan-school` service → **Environment**.
6. Add environment variable:
   - **Key**: `DATABASE_URL`
   - **Value**: *(Paste your Supabase URI)*
7. Click **Save Changes**.

---

## 🐘 Option C: Render Native PostgreSQL

Render also offers PostgreSQL databases directly inside the Render dashboard:
1. On **Render Dashboard**, click **New +** → **PostgreSQL**.
2. Name it `school-db` and select **Free Tier**.
3. Once created, copy the **Internal Database URL**.
4. In your `chandrabhan-school` Web Service → **Environment**, add:
   - **Key**: `DATABASE_URL`
   - **Value**: *(Paste Internal Database URL)*

---

## 🩺 Troubleshooting: "data disappears after a restart"

That symptom means the app is running on SQLite, not PostgreSQL. Check in this order.

**1. Confirm what the app is actually using.**
Open `https://<your-app>.onrender.com/health/db`. You want:
```json
{"status": "ok", "engine": "postgresql", "permanent": true}
```
Anything else means writes are not permanent. Director → **Storage Diagnostics**
shows the same thing plus the last database error.

**2. If the deploy fails to start, read the log.** The app now refuses to boot
rather than falling back to SQLite, and prints the exact reason:

| Log message | Cause | Fix |
|---|---|---|
| `DATABASE_URL is not set` | env var missing from the service | Add it under Render → Environment |
| `no PostgreSQL driver could be imported` | `psycopg2` will not import for the running Python | Keep `.python-version` pinned; `psycopg2-binary` has no wheels for Python 3.13 |
| `must be a PostgreSQL URL` | the value is not a `postgres://` / `postgresql://` URL | Paste the full Neon connection string |
| `Could not establish the PostgreSQL connection` | Neon unreachable after 5 retries | Check the Neon project is not suspended, and that the password in the URL is current |
| `SECRET_KEY is not set` | env var missing | Add a long random `SECRET_KEY` |

**3. Verify persistence end to end.** Note the row counts on Storage
Diagnostics, add a student, trigger a manual redeploy, then reload the page. On
PostgreSQL the count stays up by one.

> **Why this used to fail silently:** Flask-SQLAlchemy builds the database engine
> inside `db.init_app(app)`. Older code tried to re-bind PostgreSQL from a
> `@before_request` hook, which changes the config but not the already-built
> engine — so the app kept writing to SQLite while the dashboard badge claimed
> PostgreSQL. The URI is now resolved once, before `init_app`, and every status
> badge reads the live engine instead of the config string.

---

## 💾 Local Backup & Restore System

Inside the application, management can also perform **one-click offline backups** at any time:
1. Log in as Director.
2. Click **System Backup & Restore** (`/director/backup`).
3. Click **Download Full School Backup (.json)** to save a timestamped snapshot of all rosters, logs, and attendance history to your local computer.
4. If you ever switch database providers, upload the backup file via **Upload & Restore School Data** to restore all records instantly!

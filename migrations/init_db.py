"""
Database initializer for Chandrabhan Singh Public School.
Initializes tables, master accounts, and academic session structure.

CRITICAL PRODUCTION RULES:
  - NEVER drops existing tables or overwrites existing user data.
  - Creates master accounts ONLY if the database is completely empty.
  - Zero dummy data (no sample students, daily logs, attendance, or pillar scores).
  - NO hardcoded passwords. Bootstrap credentials come from environment
    variables, or are randomly generated and printed once to the deploy log.
    A password literal committed to the repository hands a super-admin account
    to anyone who can read the source.
"""
import os
import sys
import secrets

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import User, Class, TeacherClassSubject


def _bootstrap_password(env_var: str) -> tuple[str, bool]:
    """
    Read a bootstrap password from the environment, or generate a strong random
    one. Returns (password, was_generated) so generated values can be surfaced
    exactly once at creation time.
    """
    supplied = os.environ.get(env_var, '').strip()
    if supplied:
        return supplied, False
    return secrets.token_urlsafe(12), True


def seed(app_instance=None):
    if app_instance is None:
        app = create_app(os.environ.get('FLASK_ENV', 'development'))
    else:
        app = app_instance

    with app.app_context():
        # Ensure missing tables are created without dropping existing data
        db.create_all()

        # If user table already has data, preserve existing database permanently
        if User.query.first():
            print("[INFO] Existing database detected. Preserving all records and user data.")
            return

        print("[*] Empty database detected. Initializing master accounts & academic structure...")

        generated_credentials = []

        # ── 1. Master Login Accounts ───────────────────────────────────────
        admin_pw, admin_generated = _bootstrap_password('BOOTSTRAP_ADMIN_PASSWORD')
        admin = User(username='principal', full_name='Principal Admin', role='admin')
        admin.set_password(admin_pw)
        db.session.add(admin)
        if admin_generated:
            generated_credentials.append(('principal', admin_pw))
        print("[OK] Admin account created: principal")

        director_pw, director_generated = _bootstrap_password('BOOTSTRAP_DIRECTOR_PASSWORD')
        director = User(username='director', full_name='Director / Super-Admin', role='director')
        director.set_password(director_pw)
        db.session.add(director)
        if director_generated:
            generated_credentials.append(('director', director_pw))
        print("[OK] Director super-admin account created: director")

        teacher_data = [
            ('teacher1', 'Mrs. Sunita Devi'),
            ('teacher2', 'Mr. Ramesh Kumar'),
            ('teacher3', 'Mrs. Priya Sharma'),
            ('teacher4', 'Mr. Ajay Singh'),
            ('teacher5', 'Mrs. Kavita Rao'),
        ]
        shared_teacher_pw = os.environ.get('BOOTSTRAP_TEACHER_PASSWORD', '').strip()

        teachers = []
        for uname, fname in teacher_data:
            t = User(username=uname, full_name=fname, role='teacher')
            if shared_teacher_pw:
                t.set_password(shared_teacher_pw)
            else:
                pw = secrets.token_urlsafe(12)
                t.set_password(pw)
                generated_credentials.append((uname, pw))
            db.session.add(t)
            db.session.flush()
            teachers.append(t)
        print(f"[OK] {len(teachers)} default teacher accounts ready.")

        # ── 2. Class Structure (Nursery to Class 10, Sections A & B) ───────
        academic_year = app.config.get('ACADEMIC_YEAR', '2026-27')
        classes = []
        grades = [-3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        sections = ['A', 'B']

        for g in grades:
            for sec in sections:
                cls = Class.query.filter_by(grade=g, section=sec, academic_year=academic_year).first()
                if not cls:
                    cls = Class(grade=g, section=sec, academic_year=academic_year)
                    db.session.add(cls)
                    db.session.flush()
                classes.append(cls)
        print(f"[OK] {len(classes)} class sections initialized for Academic Year {academic_year}.")

        # Assign teacher1 as default class teacher for Nursery-A
        nursery_a = next((c for c in classes if c.grade == -3 and c.section == 'A'), None)
        if nursery_a and teachers[0]:
            teachers[0].assigned_class_id = nursery_a.id

        # ── 3. Initial Teacher Class-Subject Mappings ─────────────────────
        cls_4a = next((c for c in classes if c.grade == 4 and c.section == 'A'), classes[0])
        cls_5a = next((c for c in classes if c.grade == 5 and c.section == 'A'), classes[1])

        mappings = [
            (teachers[0].id, classes[0].id, 'General'),
            (teachers[1].id, classes[1].id, 'General'),
            (teachers[2].id, classes[2].id, 'General'),
            (teachers[3].id, cls_4a.id, 'English'),
            (teachers[3].id, cls_5a.id, 'English'),
            (teachers[3].id, cls_4a.id, 'Reasoning'),
            (teachers[4].id, cls_4a.id, 'Mathematics'),
            (teachers[4].id, cls_5a.id, 'Mathematics'),
            (teachers[4].id, cls_5a.id, 'Reasoning'),
        ]
        for t_id, c_id, subj in mappings:
            existing = TeacherClassSubject.query.filter_by(teacher_id=t_id, class_id=c_id, subject=subj).first()
            if not existing:
                db.session.add(TeacherClassSubject(teacher_id=t_id, class_id=c_id, subject=subj))
        db.session.flush()
        print("[OK] Default teacher class-subject mappings initialized.")

        db.session.commit()

        print("\n[DONE] Production database setup complete (Zero dummy logs/records).")
        print("-" * 70)
        print(f"  Academic Session: {academic_year}")
        if generated_credentials:
            print("  ONE-TIME GENERATED PASSWORDS — copy these now, they are not stored")
            print("  anywhere in readable form and will NOT be shown again:")
            for uname, pw in generated_credentials:
                print(f"    {uname:<12} {pw}")
            print("  Set BOOTSTRAP_ADMIN_PASSWORD / BOOTSTRAP_DIRECTOR_PASSWORD /")
            print("  BOOTSTRAP_TEACHER_PASSWORD to choose these yourself instead.")
        else:
            print("  Passwords were taken from the BOOTSTRAP_*_PASSWORD environment variables.")
        print("-" * 70)


if __name__ == '__main__':
    # Some deployments still call this from their build step. Seeding also runs
    # automatically at startup, so a failure here (for example, the build
    # machine cannot reach the database) must not fail the whole deploy.
    try:
        seed()
    except Exception as exc:
        print(f'[WARN] Could not seed during build: {type(exc).__name__}: {exc}')
        print('[WARN] This is not fatal. The application seeds itself on startup.')

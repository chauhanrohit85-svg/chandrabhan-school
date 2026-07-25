"""
Database initializer for Chandrabhan Singh Public School.
Initializes tables, default master accounts, and academic session structure (2026-27).

CRITICAL PRODUCTION RULES:
  - NEVER drops existing tables or overwrites existing user data.
  - Creates master accounts ONLY if the database is completely empty.
  - Zero dummy data (no sample students, daily logs, attendance, or pillar scores).
"""
import sys
import os

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import User, Class, TeacherClassSubject


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

        print("[*] Empty database detected. Initializing master accounts & academic structure (2026-27)...")

        # ── 1. Master Login Accounts ───────────────────────────────────────
        if not User.query.filter_by(username='principal').first():
            admin = User(username='principal', full_name='Principal Admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            print("[OK] Admin account created: principal / admin123")

        if not User.query.filter_by(username='director').first():
            director = User(username='director', full_name='Director / Super-Admin', role='director')
            director.set_password('director123')
            db.session.add(director)
            print("[OK] Director super-admin account created: director / director123")

        teacher_data = [
            ('teacher1', 'Mrs. Sunita Devi',  'teacher123'),
            ('teacher2', 'Mr. Ramesh Kumar',   'teacher123'),
            ('teacher3', 'Mrs. Priya Sharma',  'teacher123'),
            ('teacher4', 'Mr. Ajay Singh',     'teacher123'),
            ('teacher5', 'Mrs. Kavita Rao',    'teacher123'),
        ]
        teachers = []
        for uname, fname, pw in teacher_data:
            t = User.query.filter_by(username=uname).first()
            if not t:
                t = User(username=uname, full_name=fname, role='teacher')
                t.set_password(pw)
                db.session.add(t)
                db.session.flush()
            teachers.append(t)
        print(f"[OK] {len(teachers)} default teacher accounts ready.")

        # ── 2. Class Structure (Nursery to Class 10, Sections A & B - 2026-27) ─
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
        print("-" * 50)
        print(f"  Academic Session: {academic_year}")
        print("  Director login:   director / director123")
        print("  Admin login:      principal / admin123")
        print("  Teacher logins:   teacher1-teacher5 / teacher123")
        print("-" * 50)


if __name__ == '__main__':
    seed()

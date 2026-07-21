"""
Database initializer and seeder for Chandrabhan Singh Public School.
Run once: python migrations/init_db.py

Creates all tables and seeds:
  - 1 admin (principal)
  - 5 teachers with multi-class/subject mappings
  - 8 classes (Class 1-8, Section A)
  - 10 students per class (80 total)
  - Attendance records for the last 5 days
  - Pillar scores for the last 4 weeks with subject mappings
  - Teacher daily logs with subjects
"""
import sys
import os

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta
from app import create_app
from app.extensions import db
from app.models import (User, Class, Student, TeacherDailyLog, AttendanceRecord,
                        PillarScore, AlertFlag, TeacherClassSubject)


def seed(app_instance=None):
    if app_instance is None:
        app = create_app('development')
        drop_tables = True
    else:
        app = app_instance
        drop_tables = False

    with app.app_context():
        if not drop_tables:
            # Check if database is already seeded
            if User.query.filter_by(username='principal').first():
                return

        print("[*] Recreating all tables..." if drop_tables else "[*] Initializing database...")
        if drop_tables:
            db.drop_all()
        db.create_all()
        print("[OK] Tables recreated." if drop_tables else "[OK] Tables created.")

        # ── Admin ──────────────────────────────────────────────────────────
        if not User.query.filter_by(username='principal').first():
            admin = User(username='principal', full_name='Principal Admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            print("[OK] Admin account created: principal / admin123")

        # ── Classes ────────────────────────────────────────────────────────
        academic_year = app.config['ACADEMIC_YEAR']
        classes = []
        for grade in range(1, 9):
            for section in ['A']:
                cls = Class.query.filter_by(grade=grade, section=section,
                                            academic_year=academic_year).first()
                if not cls:
                    cls = Class(grade=grade, section=section, academic_year=academic_year)
                    db.session.add(cls)
                    db.session.flush()
                classes.append(cls)
        print(f"[OK] {len(classes)} classes ready.")

        # ── Teachers ───────────────────────────────────────────────────────
        teacher_data = [
            ('teacher1', 'Mrs. Sunita Devi',  'teacher123'),
            ('teacher2', 'Mr. Ramesh Kumar',   'teacher123'),
            ('teacher3', 'Mrs. Priya Sharma',  'teacher123'),
            ('teacher4', 'Mr. Ajay Singh',     'teacher123'),
            ('teacher5', 'Mrs. Kavita Rao',    'teacher123'),
        ]
        teachers = []
        for i, (uname, fname, pw) in enumerate(teacher_data):
            t = User.query.filter_by(username=uname).first()
            if not t:
                # Class 1-3 are primary, single class teachers
                # Class 4 and 5 are multi-class subject teachers (teacher4 & teacher5)
                t = User(username=uname, full_name=fname, role='teacher',
                         assigned_class_id=classes[i].id if i < 3 else None)
                t.set_password(pw)
                db.session.add(t)
                db.session.flush()
            teachers.append(t)
        print(f"[OK] {len(teachers)} teacher accounts ready.")

        # ── Multi-Class Mappings (For Class 4th & above / Subject Teachers) ──
        # Mappings: Teacher -> Class -> Subject
        mappings = [
            # Teacher 1, 2, 3 (Primary, Grade 1, 2, 3) get 'General' mappings
            (teachers[0].id, classes[0].id, 'General'),
            (teachers[1].id, classes[1].id, 'General'),
            (teachers[2].id, classes[2].id, 'General'),
            # Teacher 4: teaches English in Class 4-A and 5-A, and Reasoning in Class 4-A
            (teachers[3].id, classes[3].id, 'English'),
            (teachers[3].id, classes[4].id, 'English'),
            (teachers[3].id, classes[3].id, 'Reasoning'),
            # Teacher 5: teaches Mathematics in Class 4-A and Class 5-A, and Reasoning in Class 5-A
            (teachers[4].id, classes[3].id, 'Mathematics'),
            (teachers[4].id, classes[4].id, 'Mathematics'),
            (teachers[4].id, classes[4].id, 'Reasoning'),
        ]
        for t_id, c_id, subj in mappings:
            mapping = TeacherClassSubject(teacher_id=t_id, class_id=c_id, subject=subj)
            db.session.add(mapping)
        db.session.flush()
        print("[OK] Teacher Class-Subject mappings seeded.")

        # ── Students (10 per class 1-5, assigned to first 5 classes) ─────
        sample_names = [
            'Aarav Sharma', 'Ananya Gupta', 'Rohan Verma', 'Ishita Patel',
            'Vikram Singh', 'Pooja Mishra', 'Arjun Yadav', 'Meera Joshi',
            'Karan Agarwal', 'Divya Pandey',
        ]
        student_map = {}  # class_id -> [students]
        for cls in classes[:5]:
            student_map[cls.id] = []
            for j, name in enumerate(sample_names):
                roll = f'{j+1:02d}'
                s = Student.query.filter_by(roll_number=roll, class_id=cls.id).first()
                if not s:
                    s = Student(
                        roll_number=roll,
                        full_name=name,
                        class_id=cls.id,
                        parent_contact=f'+91 98{cls.grade}00{j+1:04d}'
                    )
                    db.session.add(s)
                    db.session.flush()
                student_map[cls.id].append(s)
        print("[OK] Students seeded.")

        # ── Daily Logs (last 5 days for each mapped subject) ──────────────────────
        syllabus_data = [
            ('Chapter 3: Multiplication Tables', 'on_track'),
            ('Chapter 4: Division Basics', 'on_track'),
            ('Chapter 5: Fractions', 'delayed'),
            ('Chapter 6: Word Problems', 'ahead'),
            ('Chapter 7: Measurement', 'on_track'),
        ]
        today = date.today()
        # Seed logs based on the assigned mapping list to align with new architecture
        for t_id, c_id, subj in mappings:
            for d in range(5):
                log_date = today - timedelta(days=d)
                topic, status = syllabus_data[d]
                log = TeacherDailyLog(
                    teacher_id=t_id,
                    class_id=c_id,
                    log_date=log_date,
                    lesson_completed=1,
                    syllabus_topic=f'[{subj}] {topic}',
                    syllabus_status=status,
                    subject=subj,
                    homework_assigned=1 if d % 2 == 0 else 0,
                    remarks=f'Class went well for {subj}.' if d == 0 else ''
                )
                db.session.add(log)
        print("[OK] Daily logs seeded.")

        # ── Attendance (last 7 days) ───────────────────────────────────────
        import random
        random.seed(42)
        for cls_id, students in student_map.items():
            # Find any teacher mapped to this class
            mapped_teacher = TeacherClassSubject.query.filter_by(class_id=cls_id).first()
            teacher_id = mapped_teacher.teacher_id if mapped_teacher else teachers[0].id

            for s in students:
                for d in range(7):
                    att_date = today - timedelta(days=d)
                    # ~85% present, ~10% absent, ~5% late
                    rand = random.random()
                    status = 'present' if rand < 0.85 else ('late' if rand < 0.90 else 'absent')
                    db.session.add(AttendanceRecord(
                        student_id=s.id,
                        log_date=att_date,
                        status=status,
                        marked_by=teacher_id
                    ))
        print("[OK] Attendance records seeded.")

        # ── Pillar Scores (last 4 weeks) ───────────────────────────────────
        now = datetime.now()
        current_week = now.isocalendar()[1]
        current_year = now.year

        for cls_id, students in student_map.items():
            # Find all subjects taught in this class from mappings
            class_mappings = TeacherClassSubject.query.filter_by(class_id=cls_id).all()
            if not class_mappings:
                continue

            for s in students:
                for wk_offset in range(4):
                    wk = max(1, current_week - wk_offset)
                    for mapping in class_mappings:
                        # Map pillars to corresponding subjects
                        # If mapping is General, write for all pillars under General
                        # If English, write for reading, writing, english_speaking
                        # If Mathematics, write for mathematics
                        # If Reasoning, write for reasoning
                        subj = mapping.subject
                        matching_pillars = []
                        if subj == 'General':
                            matching_pillars = PillarScore.PILLARS
                        elif subj == 'English':
                            matching_pillars = ['english_speaking', 'reading', 'writing']
                        elif subj == 'Mathematics':
                            matching_pillars = ['mathematics']
                        elif subj == 'Reasoning':
                            matching_pillars = ['reasoning']

                        for pillar in matching_pillars:
                            # 80% of students score 3-5, 20% score 1-2 (for alerts)
                            qual = random.choices([1,2,3,4,5],
                                                  weights=[5,10,25,35,25])[0]
                            db.session.add(PillarScore(
                                student_id=s.id,
                                pillar=pillar,
                                subject=subj,
                                week_number=wk,
                                year=current_year,
                                qualitative=qual,
                                quantitative_score=round(qual * 18 + random.uniform(-5, 5), 1),
                                remarks='[Attentive]' if qual >= 4 else '[Needs Practice]',
                                recorded_by=mapping.teacher_id
                            ))
        print("[OK] Pillar scores seeded.")

        db.session.commit()
        print("\n[DONE] Database initialization complete!")
        print("-" * 50)
        print("  Admin login:    principal / admin123")
        print("  Teacher logins: teacher1-teacher5 / teacher123")
        print(f"  URL:            http://localhost:5000")
        print("-" * 50)


if __name__ == '__main__':
    seed()

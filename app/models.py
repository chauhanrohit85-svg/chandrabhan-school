"""
SQLAlchemy ORM models for all 7 database tables.
WAL journal mode is set in the app factory for SQLite concurrency.
"""
from datetime import datetime, date
from app.extensions import db, login_manager
from flask_login import UserMixin
import bcrypt


# ---------------------------------------------------------------------------
# User Model
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)          # admin | teacher | tv
    assigned_class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=True)
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assigned_class = db.relationship('Class', backref='assigned_teacher',
                                     foreign_keys=[assigned_class_id])
    daily_logs = db.relationship('TeacherDailyLog', backref='teacher',
                                 foreign_keys='TeacherDailyLog.teacher_id',
                                 lazy='dynamic')

    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(
            password.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(
            password.encode('utf-8'), self.password_hash.encode('utf-8')
        )

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_teacher_role(self):
        return self.role == 'teacher'

    def __repr__(self):
        return f'<User {self.username} [{self.role}]>'


# ---------------------------------------------------------------------------
# TeacherClassSubject Mapping Model (For Class 4th & above multi-class)
# ---------------------------------------------------------------------------
class TeacherClassSubject(db.Model):
    __tablename__ = 'teacher_class_subjects'

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    subject = db.Column(db.String(50), nullable=False)  # e.g., English, Mathematics, Science, Reasoning

    teacher = db.relationship('User', backref=db.backref('class_subjects', lazy='dynamic', cascade='all, delete-orphan'))
    class_ref = db.relationship('Class', backref=db.backref('teacher_subjects', lazy='dynamic', cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'class_id', 'subject', name='uq_teacher_class_subject'),
    )

    def __repr__(self):
        return f'<TeacherClassSubject {self.teacher_id} -> Class:{self.class_id} Subj:{self.subject}>'


# ---------------------------------------------------------------------------
# Class Model
# ---------------------------------------------------------------------------
class Class(db.Model):
    __tablename__ = 'classes'

    GRADE_MAP = {
        -3: 'Nursery',
        -2: 'LKG',
        -1: 'UKG',
        1: 'Class 1',
        2: 'Class 2',
        3: 'Class 3',
        4: 'Class 4',
        5: 'Class 5',
        6: 'Class 6',
        7: 'Class 7',
        8: 'Class 8',
        9: 'Class 9',
        10: 'Class 10',
    }
    GRADE_ORDER = [-3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.Integer, nullable=False)             # -3 (Nursery) .. 10 (Class 10)
    section = db.Column(db.String(5), nullable=False)         # A / B
    academic_year = db.Column(db.String(10), nullable=False)  # "2025-26"

    students = db.relationship('Student', backref='class_ref', lazy='dynamic')
    logs = db.relationship('TeacherDailyLog', backref='class_ref', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('grade', 'section', 'academic_year',
                            name='uq_class_grade_section_year'),
    )

    @property
    def display_name(self):
        name = self.GRADE_MAP.get(self.grade, f'Class {self.grade}')
        return f'{name}-{self.section}'

    @property
    def is_primary(self):
        return self.grade <= 3

    def __repr__(self):
        return f'<Class {self.display_name} ({self.academic_year})>'


# ---------------------------------------------------------------------------
# Student Model
# ---------------------------------------------------------------------------
class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    parent_contact = db.Column(db.String(20))
    is_active = db.Column(db.Integer, default=1)

    attendance_records = db.relationship('AttendanceRecord', backref='student',
                                         lazy='dynamic',
                                         cascade='all, delete-orphan')
    pillar_scores = db.relationship('PillarScore', backref='student',
                                    lazy='dynamic',
                                    cascade='all, delete-orphan')
    alert_flags = db.relationship('AlertFlag', backref='student',
                                  lazy='dynamic',
                                  cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('roll_number', 'class_id', name='uq_student_roll_class'),
    )

    def __repr__(self):
        return f'<Student {self.full_name} [{self.roll_number}]>'


# ---------------------------------------------------------------------------
# TeacherDailyLog Model
# ---------------------------------------------------------------------------
class TeacherDailyLog(db.Model):
    __tablename__ = 'teacher_daily_logs'

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    log_date = db.Column(db.Date, nullable=False, default=date.today)
    lesson_completed = db.Column(db.Integer, default=0)       # boolean 0/1
    syllabus_topic = db.Column(db.String(200))
    syllabus_status = db.Column(db.String(20), default='on_track')  # on_track | delayed | ahead
    subject = db.Column(db.String(50), nullable=True, default='General')  # Added for multi-class period mapping
    photo_base64 = db.Column(db.Text, nullable=True)  # Compressed image base64 string (<200KB)
    homework_assigned = db.Column(db.Integer, default=0)      # boolean 0/1
    remarks = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'class_id', 'subject', 'log_date',
                            name='uq_log_teacher_class_subject_date'),
    )

    SYLLABUS_STATUS_LABELS = {
        'on_track': 'On Track',
        'delayed': 'Delayed',
        'ahead': 'Ahead of Schedule',
    }

    def __repr__(self):
        return f'<TeacherDailyLog {self.teacher_id} {self.log_date} {self.subject}>'


# ---------------------------------------------------------------------------
# AttendanceRecord Model
# ---------------------------------------------------------------------------
class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    log_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(10), nullable=False)          # present | absent | late
    marked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_edited = db.Column(db.Integer, default=0)              # 1 if rectified retroactively
    edited_at = db.Column(db.DateTime, nullable=True)          # Timestamp of rectification

    marker = db.relationship('User', foreign_keys=[marked_by])

    __table_args__ = (
        db.UniqueConstraint('student_id', 'log_date', name='uq_attendance_student_date'),
    )

    def __repr__(self):
        return f'<AttendanceRecord {self.student_id} {self.log_date} {self.status} Edited:{self.is_edited}>'


# ---------------------------------------------------------------------------
# PillarScore Model
# ---------------------------------------------------------------------------
class PillarScore(db.Model):
    __tablename__ = 'pillar_scores'

    PILLARS = ['english_speaking', 'mathematics', 'reasoning', 'reading', 'writing']
    PILLAR_LABELS = {
        'english_speaking': 'English Speaking',
        'mathematics': 'Mathematics',
        'reasoning': 'Reasoning',
        'reading': 'Reading',
        'writing': 'Writing',
    }
    PILLAR_ICONS = {
        'english_speaking': '🗣️',
        'mathematics': '🔢',
        'reasoning': '🧠',
        'reading': '📖',
        'writing': '✍️',
    }
    QUALITATIVE_LABELS = {
        1: 'Needs Work',
        2: 'Developing',
        3: 'Satisfactory',
        4: 'Good',
        5: 'Excellent',
    }

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    pillar = db.Column(db.String(30), nullable=False)
    subject = db.Column(db.String(50), nullable=True, default='General')  # Added subject specificity
    week_number = db.Column(db.Integer, nullable=False)        # ISO week 1–53
    year = db.Column(db.Integer, nullable=False)
    qualitative = db.Column(db.Integer, nullable=False)        # 1–5
    quantitative_score = db.Column(db.Float)                   # 0–100
    remarks = db.Column(db.String(255), nullable=True)         # Stores quick milestone remark tags
    photo_base64 = db.Column(db.Text, nullable=True)           # Base64 photo attachment (<200KB)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    recorder = db.relationship('User', foreign_keys=[recorded_by])

    __table_args__ = (
        db.UniqueConstraint('student_id', 'pillar', 'subject', 'week_number', 'year',
                            name='uq_pillar_student_subject_week'),
    )

    def __repr__(self):
        return f'<PillarScore {self.student_id} {self.pillar} W{self.week_number} {self.subject}>'


# ---------------------------------------------------------------------------
# AlertFlag Model
# ---------------------------------------------------------------------------
class AlertFlag(db.Model):
    __tablename__ = 'alert_flags'

    ALERT_TYPE_LABELS = {
        'below_threshold': 'Below Threshold',
        'consistent_decline': 'Consistent Decline',
        'absent_streak': 'Absence Streak',
    }
    ALERT_TYPE_COLORS = {
        'below_threshold': 'amber',
        'consistent_decline': 'red',
        'absent_streak': 'orange',
    }

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    pillar = db.Column(db.String(30))                          # NULL = general
    alert_type = db.Column(db.String(30), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_resolved = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AlertFlag {self.student_id} {self.alert_type}>'


# ---------------------------------------------------------------------------
# Flask-Login user loader
# ---------------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

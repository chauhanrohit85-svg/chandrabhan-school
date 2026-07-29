"""
TV display routes — read-only, high-contrast class views.

These pages show student names, roll numbers, attendance and alert text, so they
require a login like every other page. Previously they were reachable by anyone
who guessed /tv/<class_id>, which published the roster of a class to the open
internet.

For a classroom Smart TV, create a user with role='tv' and an assigned class,
sign in once on the TV browser with "Keep me signed in", and the kiosk stays
authenticated across restarts. A 'tv' user can only open its own class; staff
can open any class.
"""
from functools import wraps
from datetime import date, datetime

from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from app.tv import tv_bp
from app.models import Class, Student, AttendanceRecord, PillarScore, AlertFlag, TeacherClassSubject
from app.extensions import db

_STAFF_ROLES = ('admin', 'director', 'teacher')


def tv_viewer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in _STAFF_ROLES + ('tv',):
            flash('Please sign in to view the classroom display.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _may_view_class(class_id: int) -> bool:
    if current_user.role in _STAFF_ROLES:
        return True
    # A kiosk account is pinned to the single class it was created for.
    return current_user.assigned_class_id == class_id


@tv_bp.route('/<int:class_id>')
@login_required
@tv_viewer_required
def class_view(class_id):
    cls = Class.query.get_or_404(class_id)

    if not _may_view_class(class_id):
        flash('This display is not authorised for that class.', 'danger')
        return redirect(url_for('auth.login'))

    today = date.today()

    students = Student.query.filter_by(class_id=class_id, is_active=1)\
                            .order_by(Student.roll_number).all()

    # Attendance summary
    total = len(students)
    present = AttendanceRecord.query.filter_by(log_date=today, status='present')\
                .join(Student).filter(Student.class_id == class_id).count()
    absent = AttendanceRecord.query.filter_by(log_date=today, status='absent')\
                .join(Student).filter(Student.class_id == class_id).count()
    late = AttendanceRecord.query.filter_by(log_date=today, status='late')\
                .join(Student).filter(Student.class_id == class_id).count()

    # Pillar averages (last 4 weeks) - General class-wide
    now = datetime.now()
    current_week = now.isocalendar()[1]
    current_year = now.year
    start_week = max(1, current_week - 3)

    pillar_avgs = {}
    for pillar in PillarScore.PILLARS:
        result = db.session.query(func.avg(PillarScore.qualitative))\
            .join(Student).filter(
                Student.class_id == class_id,
                PillarScore.pillar == pillar,
                PillarScore.year == current_year,
                PillarScore.week_number >= start_week
            ).scalar()
        pillar_avgs[pillar] = round(result * 20, 1) if result else 0  # convert 1-5 → 0-100

    # Fetch unique subjects mapped to this class to enable overlay toggle
    subjects_query = db.session.query(TeacherClassSubject.subject)\
                               .filter_by(class_id=class_id).distinct().all()
    subjects = [s[0] for s in subjects_query]
    if 'General' not in subjects:
        subjects.append('General')

    # Pre-calculate averages for each mapped subject
    subject_radar_data = {}
    for subj in subjects:
        subject_radar_data[subj] = {}
        for pillar in PillarScore.PILLARS:
            res = db.session.query(func.avg(PillarScore.qualitative))\
                .join(Student).filter(
                    Student.class_id == class_id,
                    PillarScore.pillar == pillar,
                    PillarScore.subject == subj,
                    PillarScore.year == current_year,
                    PillarScore.week_number >= start_week
                ).scalar()
            subject_radar_data[subj][pillar] = round(res * 20, 1) if res else 0

    # Active alerts for this class
    alerts = AlertFlag.query.filter_by(is_resolved=0)\
                .join(Student).filter(Student.class_id == class_id)\
                .order_by(AlertFlag.created_at.desc()).limit(5).all()

    # Per-student attendance list (with audit edited fields)
    attendance_map = {}
    attendance_details = {}
    for rec in AttendanceRecord.query.filter_by(log_date=today)\
                .join(Student).filter(Student.class_id == class_id).all():
        attendance_map[rec.student_id] = rec.status
        attendance_details[rec.student_id] = {
            'is_edited': rec.is_edited,
            'edited_at': rec.edited_at.isoformat() if rec.edited_at else None
        }

    return render_template('tv/class_view.html',
        cls=cls,
        students=students,
        today=today,
        total=total,
        present=present,
        absent=absent,
        late=late,
        pillar_avgs=pillar_avgs,
        pillar_labels=PillarScore.PILLAR_LABELS,
        pillar_icons=PillarScore.PILLAR_ICONS,
        subjects=subjects,
        subject_radar_data=subject_radar_data,
        alerts=alerts,
        attendance_map=attendance_map,
        attendance_details=attendance_details,
        refresh_seconds=300,
    )


@tv_bp.route('/list')
@login_required
@tv_viewer_required
def class_list():
    """Simple list of all classes with TV links."""
    if current_user.role not in _STAFF_ROLES:
        # Kiosk accounts go straight to their own class rather than a chooser.
        if current_user.assigned_class_id:
            return redirect(url_for('tv.class_view', class_id=current_user.assigned_class_id))
        flash('This display has no class assigned. Ask an administrator to set one.', 'warning')
        return redirect(url_for('auth.login'))

    classes = Class.query.order_by(Class.grade, Class.section).all()
    return render_template('tv/class_list.html', classes=classes)


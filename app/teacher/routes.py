"""
Teacher module routes.
All forms auto-save via autosave.js and sync via sync.js.
Supports multi-class subject periods, photo uploads, and retroactive attendance.
"""
from flask import render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_required, current_user
from functools import wraps
from datetime import date, datetime, timedelta
from app.teacher import teacher_bp
from app.extensions import db
from app.models import (User, Class, Student, TeacherDailyLog,
                        AttendanceRecord, PillarScore, AlertFlag, TeacherClassSubject)


def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('teacher', 'admin'):
            flash('Access denied.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def get_active_context():
    """Retrieve active Class, Subject, and mapped list for current user."""
    mappings = current_user.class_subjects.all()
    
    # Try getting from query params first, otherwise session
    switch_id = request.args.get('active_mapping_id', type=int)
    if not switch_id:
        switch_id = session.get('active_mapping_id')
        
    active_mapping = None
    if switch_id:
        active_mapping = TeacherClassSubject.query.filter_by(id=switch_id, teacher_id=current_user.id).first()
        
    if not active_mapping and mappings:
        active_mapping = mappings[0]
        
    if active_mapping:
        session['active_mapping_id'] = active_mapping.id
        return active_mapping.class_ref, active_mapping.subject, mappings
        
    # Fallback to legacy assigned_class_id
    cls = current_user.assigned_class
    subject = 'General'
    return cls, subject, []


def _pillars_for_subject(subject):
    """Only show the pillars a subject teacher can actually judge."""
    if subject == 'English':
        return ['english_speaking', 'reading', 'writing']
    if subject == 'Mathematics':
        return ['mathematics']
    if subject == 'Reasoning':
        return ['reasoning']
    return PillarScore.PILLARS


def get_syllabus_pace(class_id, subject):
    """
    Calculate progress of syllabus relative to time elapsed in the term.
    Target: 40 lessons completed per term.
    """
    today = date.today()
    year = today.year
    
    # Term 1: April 1 -> Sept 30, Term 2: Oct 1 -> March 31
    if today.month >= 4 and today.month <= 9:
        term_start = date(year, 4, 1)
        term_end = date(year, 9, 30)
    elif today.month >= 10:
        term_start = date(year, 10, 1)
        term_end = date(year + 1, 3, 31)
    else:
        term_start = date(year - 1, 10, 1)
        term_end = date(year, 3, 31)
        
    total_days = (term_end - term_start).days
    elapsed_days = (today - term_start).days
    elapsed_days = max(0, min(elapsed_days, total_days))
    
    percent_elapsed = round((elapsed_days / total_days) * 100, 1) if total_days > 0 else 0
    
    completed_lessons = TeacherDailyLog.query.filter(
        TeacherDailyLog.class_id == class_id,
        TeacherDailyLog.subject == subject,
        TeacherDailyLog.lesson_completed == 1,
        TeacherDailyLog.log_date >= term_start,
        TeacherDailyLog.log_date <= term_end
    ).count()
    
    TARGET_LESSONS = 40
    percent_covered = round((completed_lessons / TARGET_LESSONS) * 100, 1)
    percent_covered = min(100.0, percent_covered)
    
    diff = percent_covered - percent_elapsed
    if diff >= 5:
        status = 'ahead'
        status_label = 'Ahead of Schedule'
    elif diff < -10:
        status = 'delayed'
        status_label = 'Lagging Behind'
    else:
        status = 'on_track'
        status_label = 'On Track'
        
    return {
        'percent_elapsed': percent_elapsed,
        'percent_covered': percent_covered,
        'status': status,
        'status_label': status_label,
        'completed': completed_lessons,
        'target': TARGET_LESSONS
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@teacher_bp.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    today = date.today()
    
    # Handle switching mapping
    switch_id = request.args.get('active_mapping_id', type=int)
    if switch_id:
        session['active_mapping_id'] = switch_id
        
    cls, subject, mappings = get_active_context()

    today_log = None
    attendance_count = 0
    present_count = 0
    total_students = 0
    
    if cls:
        today_log = TeacherDailyLog.query.filter_by(
            teacher_id=current_user.id,
            class_id=cls.id,
            subject=subject,
            log_date=today
        ).first()

        students = Student.query.filter_by(class_id=cls.id, is_active=1).all()
        total_students = len(students)
        present_count = AttendanceRecord.query.filter_by(
            log_date=today, status='present'
        ).join(Student).filter(Student.class_id == cls.id).count()
        attendance_count = AttendanceRecord.query.filter_by(log_date=today)\
            .join(Student).filter(Student.class_id == cls.id).count()

    recent_logs = TeacherDailyLog.query.filter_by(
        teacher_id=current_user.id
    ).order_by(TeacherDailyLog.log_date.desc()).limit(5).all()

    syllabus_pace = get_syllabus_pace(cls.id, subject) if cls else None

    return render_template('teacher/dashboard.html',
        cls=cls,
        subject=subject,
        mappings=mappings,
        today=today,
        today_log=today_log,
        present_count=present_count,
        attendance_count=attendance_count,
        recent_logs=recent_logs,
        total_students=total_students,
        syllabus_pace=syllabus_pace,
    )


# ---------------------------------------------------------------------------
# Daily Log
# ---------------------------------------------------------------------------
@teacher_bp.route('/log/daily', methods=['GET', 'POST'])
@login_required
@teacher_required
def daily_log():
    today = date.today()
    cls, subject, mappings = get_active_context()
    if not cls:
        flash('You are not assigned to any class. Please contact the admin.', 'warning')
        return redirect(url_for('teacher.dashboard'))

    log = TeacherDailyLog.query.filter_by(
        teacher_id=current_user.id,
        class_id=cls.id,
        subject=subject,
        log_date=today
    ).first()

    if request.method == 'POST':
        lesson_completed = 1 if request.form.get('lesson_completed') else 0
        syllabus_topic = request.form.get('syllabus_topic', '').strip()
        syllabus_status = request.form.get('syllabus_status', 'on_track')
        homework_assigned = 1 if request.form.get('homework_assigned') else 0
        remarks = request.form.get('remarks', '').strip()
        photo_base64 = request.form.get('photo_base64', '').strip() or None

        if log:
            log.lesson_completed = lesson_completed
            log.syllabus_topic = syllabus_topic
            log.syllabus_status = syllabus_status
            log.homework_assigned = homework_assigned
            log.remarks = remarks
            if photo_base64:
                log.photo_base64 = photo_base64
            log.submitted_at = datetime.utcnow()
        else:
            log = TeacherDailyLog(
                teacher_id=current_user.id,
                class_id=cls.id,
                log_date=today,
                lesson_completed=lesson_completed,
                syllabus_topic=syllabus_topic,
                syllabus_status=syllabus_status,
                subject=subject,
                photo_base64=photo_base64,
                homework_assigned=homework_assigned,
                remarks=remarks,
            )
            db.session.add(log)

        try:
            db.session.commit()
            flash(f'Daily log for {subject} submitted successfully!', 'success')
            return redirect(url_for('teacher.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving daily log: {str(e)}', 'danger')

    # Everything below exists to remove typing. The topic a teacher enters is
    # almost always the next step of a topic they already entered, so previous
    # entries are offered as one-tap chips and as autocomplete suggestions.
    previous_logs = TeacherDailyLog.query.filter(
        TeacherDailyLog.teacher_id == current_user.id,
        TeacherDailyLog.class_id == cls.id,
        TeacherDailyLog.subject == subject,
        TeacherDailyLog.log_date < today,
        TeacherDailyLog.syllabus_topic.isnot(None),
        TeacherDailyLog.syllabus_topic != '',
    ).order_by(TeacherDailyLog.log_date.desc()).limit(40).all()

    last_log = previous_logs[0] if previous_logs else None

    recent_topics = []
    for prev in previous_logs:
        topic = (prev.syllabus_topic or '').strip()
        if topic and topic not in recent_topics:
            recent_topics.append(topic)
        if len(recent_topics) >= 8:
            break

    return render_template('teacher/daily_log.html',
        cls=cls,
        subject=subject,
        today=today,
        log=log,
        last_log=last_log,
        recent_topics=recent_topics,
        quick_notes=TeacherDailyLog.QUICK_NOTES,
        syllabus_statuses=TeacherDailyLog.SYLLABUS_STATUS_LABELS,
    )


# ---------------------------------------------------------------------------
# Attendance (Retroactive & Rectification audit tracking)
# ---------------------------------------------------------------------------
@teacher_bp.route('/attendance', methods=['GET', 'POST'])
@login_required
@teacher_required
def attendance():
    # Handle retroactive date selection from datepicker
    date_str = request.args.get('date')
    if date_str:
        try:
            log_date = date.fromisoformat(date_str)
        except ValueError:
            log_date = date.today()
    else:
        log_date = date.today()

    cls, subject, mappings = get_active_context()
    if not cls:
        flash('You are not assigned to any class.', 'warning')
        return redirect(url_for('teacher.dashboard'))

    students = Student.query.filter_by(class_id=cls.id, is_active=1)\
                            .order_by(Student.roll_number).all()

    if request.method == 'POST':
        submitted_count = 0
        for student in students:
            status = request.form.get(f'status_{student.id}', 'absent')
            existing = AttendanceRecord.query.filter_by(
                student_id=student.id, log_date=log_date
            ).first()

            if existing:
                if existing.status != status:
                    existing.status = status
                    existing.is_edited = 1
                    existing.edited_at = datetime.utcnow()
                    existing.marked_by = current_user.id
            else:
                rec = AttendanceRecord(
                    student_id=student.id,
                    log_date=log_date,
                    status=status,
                    marked_by=current_user.id
                )
                db.session.add(rec)
            submitted_count += 1

        try:
            db.session.commit()
            flash(f'Attendance saved for {submitted_count} students on {log_date.strftime("%d %b %Y")}.', 'success')
            return redirect(url_for('teacher.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving attendance: {str(e)}', 'danger')

    # Load existing attendance and audit details
    existing_attendance = {}
    attendance_details = {}
    for rec in AttendanceRecord.query.filter_by(log_date=log_date)\
            .join(Student).filter(Student.class_id == cls.id).all():
        existing_attendance[rec.student_id] = rec.status
        attendance_details[rec.student_id] = {
            'is_edited': rec.is_edited,
            'edited_at': rec.edited_at
        }

    return render_template('teacher/attendance.html',
        cls=cls,
        today=log_date,
        students=students,
        existing_attendance=existing_attendance,
        attendance_details=attendance_details,
    )


# ---------------------------------------------------------------------------
# Student Management (Teacher Direct Access)
# ---------------------------------------------------------------------------
@teacher_bp.route('/students')
@login_required
@teacher_required
def students():
    cls, subject, mappings = get_active_context()
    if not cls:
        flash('You are not assigned to any class context.', 'warning')
        return redirect(url_for('teacher.dashboard'))

    students_list = Student.query.filter_by(class_id=cls.id)\
                                 .order_by(Student.roll_number).all()

    return render_template('teacher/students.html',
        cls=cls,
        subject=subject,
        students=students_list,
        mappings=mappings,
    )


@teacher_bp.route('/students/add', methods=['POST'])
@login_required
@teacher_required
def add_student():
    cls, subject, mappings = get_active_context()
    if not cls:
        flash('No active class selected.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    roll = request.form.get('roll_number', '').strip()
    name = request.form.get('full_name', '').strip()
    contact = request.form.get('parent_contact', '').strip()

    if not roll or not name:
        flash('Roll number and Student name are required.', 'warning')
        return redirect(url_for('teacher.students'))

    existing = Student.query.filter_by(roll_number=roll, class_id=cls.id).first()
    if existing:
        flash(f'Roll number {roll} already exists in {cls.display_name}.', 'warning')
    else:
        try:
            student = Student(roll_number=roll, full_name=name, class_id=cls.id, parent_contact=contact)
            db.session.add(student)
            db.session.commit()
            flash(f'Student {name} added to {cls.display_name} successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding student: {str(e)}', 'danger')

    return redirect(url_for('teacher.students'))


@teacher_bp.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
@teacher_required
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)

    # Ensure teacher has context permission for this student's class
    allowed_class_ids = set()
    if current_user.assigned_class_id:
        allowed_class_ids.add(current_user.assigned_class_id)
    for m in current_user.class_subjects:
        allowed_class_ids.add(m.class_id)

    if student.class_id not in allowed_class_ids:
        flash('Permission denied. You can only edit students in your assigned classes.', 'danger')
        return redirect(url_for('teacher.students'))

    if request.method == 'POST':
        roll = request.form.get('roll_number', '').strip()
        name = request.form.get('full_name', '').strip()
        contact = request.form.get('parent_contact', '').strip()
        is_active = 1 if request.form.get('is_active') else 0

        if not roll or not name:
            flash('Roll number and full name are required.', 'warning')
            return redirect(url_for('teacher.edit_student', student_id=student_id))

        if roll != student.roll_number:
            dupe = Student.query.filter_by(roll_number=roll, class_id=student.class_id).first()
            if dupe:
                flash(f'Roll number {roll} is already in use by another student.', 'warning')
                return redirect(url_for('teacher.edit_student', student_id=student_id))

        try:
            student.roll_number = roll
            student.full_name = name
            student.parent_contact = contact
            student.is_active = is_active
            db.session.commit()
            flash(f'Student {name} updated successfully.', 'success')
            return redirect(url_for('teacher.students'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating student: {str(e)}', 'danger')

    return render_template('teacher/edit_student.html', student=student, cls=student.class_ref)


# ---------------------------------------------------------------------------
# Pillar Score Entry
# ---------------------------------------------------------------------------
@teacher_bp.route('/pillars', methods=['GET'])
@login_required
@teacher_required
def pillars():
    cls, subject, mappings = get_active_context()
    if not cls:
        flash('You are not assigned to any class.', 'warning')
        return redirect(url_for('teacher.dashboard'))

    today = date.today()
    current_week = today.isocalendar()[1]
    current_year = today.year

    students = Student.query.filter_by(class_id=cls.id, is_active=1)\
                            .order_by(Student.roll_number).all()

    existing_scores = {}
    for score in PillarScore.query.filter_by(
            subject=subject, week_number=current_week, year=current_year
    ).join(Student).filter(Student.class_id == cls.id).all():
        existing_scores[(score.student_id, score.pillar)] = score

    # Last week's ratings power the "Copy last week" shortcut. Most students do
    # not swing week to week, so copying and adjusting a handful is far less work
    # than scoring every student from scratch. Derived from a real date so it
    # stays correct across a year boundary.
    prev = today - timedelta(weeks=1)
    prev_week, prev_year = prev.isocalendar()[1], prev.isocalendar()[0]
    last_week_scores = {}
    for score in PillarScore.query.filter_by(
            subject=subject, week_number=prev_week, year=prev_year
    ).join(Student).filter(Student.class_id == cls.id).all():
        last_week_scores[f'{score.student_id}_{score.pillar}'] = score.qualitative

    return render_template('teacher/pillar_entry.html',
        cls=cls,
        subject=subject,
        students=students,
        pillars=_pillars_for_subject(subject),
        pillar_labels=PillarScore.PILLAR_LABELS,
        pillar_icons=PillarScore.PILLAR_ICONS,
        qualitative_labels=PillarScore.QUALITATIVE_LABELS,
        qualitative_colors=PillarScore.QUALITATIVE_COLORS,
        qualitative_percent=PillarScore.QUALITATIVE_PERCENT,
        milestone_tags=PillarScore.MILESTONE_TAGS,
        existing_scores=existing_scores,
        last_week_scores=last_week_scores,
        prev_week=prev_week,
        current_week=current_week,
        current_year=current_year,
    )


@teacher_bp.route('/pillars/entry', methods=['POST'])
@login_required
@teacher_required
def pillar_entry():
    cls, subject, mappings = get_active_context()
    if not cls:
        return redirect(url_for('teacher.dashboard'))

    now = datetime.now()
    current_week = int(request.form.get('week_number', now.isocalendar()[1]))
    current_year = int(request.form.get('year', now.year))

    students = Student.query.filter_by(class_id=cls.id, is_active=1).all()
    saved = 0

    active_pillars = _pillars_for_subject(subject)

    for student in students:
        for pillar in active_pillars:
            qual_key = f'qual_{student.id}_{pillar}'
            quant_key = f'quant_{student.id}_{pillar}'
            remarks_key = f'remarks_{student.id}_{pillar}'
            photo_key = f'photo_{student.id}_{pillar}_base64'

            qual_val = request.form.get(qual_key)
            if not qual_val:
                continue

            qual = int(qual_val)

            # The star rating already implies a percentage band, so the % box is
            # optional. Left blank, it is derived — that removes one number to
            # type for every student in every pillar.
            raw_quant = (request.form.get(quant_key) or '').strip()
            if raw_quant:
                try:
                    quant = float(raw_quant)
                except ValueError:
                    quant = PillarScore.QUALITATIVE_PERCENT.get(qual, 0.0)
            else:
                quant = PillarScore.QUALITATIVE_PERCENT.get(qual, 0.0)

            remarks = request.form.get(remarks_key, '').strip() or None
            photo_base64 = request.form.get(photo_key, '').strip() or None

            existing = PillarScore.query.filter_by(
                student_id=student.id,
                pillar=pillar,
                subject=subject,
                week_number=current_week,
                year=current_year
            ).first()

            if existing:
                existing.qualitative = qual
                existing.quantitative_score = quant
                existing.remarks = remarks
                if photo_base64:
                    existing.photo_base64 = photo_base64
                existing.recorded_by = current_user.id
                existing.recorded_at = datetime.utcnow()
            else:
                score = PillarScore(
                    student_id=student.id,
                    pillar=pillar,
                    subject=subject,
                    week_number=current_week,
                    year=current_year,
                    qualitative=qual,
                    quantitative_score=quant,
                    remarks=remarks,
                    photo_base64=photo_base64,
                    recorded_by=current_user.id
                )
                db.session.add(score)
            saved += 1

    try:
        db.session.commit()
        flash(f'Pillar scores for {subject} saved for Week {current_week}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving pillar scores: {str(e)}', 'danger')
    return redirect(url_for('teacher.pillars'))


# ---------------------------------------------------------------------------
# Session Promotion (Teacher Rollover)
# ---------------------------------------------------------------------------
@teacher_bp.route('/promotion', methods=['GET'])
@login_required
@teacher_required
def promotion():
    cls, subject, mappings = get_active_context()
    if not cls:
        flash('No class assigned to promote.', 'warning')
        return redirect(url_for('teacher.dashboard'))

    try:
        y1, y2 = cls.academic_year.split('-')
        next_y1 = str(int(y1) + 1)
        next_y2 = str(int(y2) + 1).zfill(2) if len(y2) == 2 else str(int(y2) + 1)
        target_year = f"{next_y1}-{next_y2}"
    except Exception:
        target_year = "2026-27"

    order = Class.GRADE_ORDER
    if cls.grade in order:
        idx = order.index(cls.grade)
        if idx < len(order) - 1:
            next_g = order[idx + 1]
            next_label = f"{Class.GRADE_MAP.get(next_g, next_g)}-{cls.section} ({target_year})"
        else:
            next_label = "Graduated"
    else:
        next_label = "Unknown"

    student_count = Student.query.filter_by(class_id=cls.id, is_active=1).count()

    return render_template('teacher/promotion.html',
        cls=cls,
        next_label=next_label,
        student_count=student_count,
        target_year=target_year,
    )


@teacher_bp.route('/promotion/execute', methods=['POST'])
@login_required
@teacher_required
def execute_promotion():
    cls, subject, mappings = get_active_context()
    if not cls:
        return redirect(url_for('teacher.dashboard'))

    target_year = request.form.get('target_year', '').strip() or '2026-27'
    from app.admin.routes import _promote_single_class
    cnt, next_name = _promote_single_class(cls, target_year)

    flash(f'Promoted {cnt} students from {cls.display_name} to {next_name} for session {target_year}!', 'success')
    return redirect(url_for('teacher.dashboard'))


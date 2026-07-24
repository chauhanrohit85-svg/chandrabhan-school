"""
Admin module routes: dashboard, reports (daily/weekly/monthly),
alerts, user management, and student management.
"""
from flask import (render_template, redirect, url_for, flash,
                   request, current_app, jsonify)
from flask_login import login_required, current_user
from functools import wraps
from datetime import date, datetime, timedelta
from sqlalchemy import func
from app.admin import admin_bp
from app.extensions import db
from app.models import (User, Class, Student, TeacherDailyLog,
                        AttendanceRecord, PillarScore, AlertFlag)


# ---------------------------------------------------------------------------
# Admin guard decorator
# ---------------------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Administrator access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Alert generation helper
# ---------------------------------------------------------------------------
def _generate_alerts():
    """Auto-flag students below threshold or with absence streaks."""
    threshold = current_app.config.get('ALERT_THRESHOLD', 2.0)
    now = datetime.now()
    current_week = now.isocalendar()[1]
    current_year = now.year
    start_week = max(1, current_week - 3)

    # 1. Pillar threshold alerts
    results = db.session.query(
        PillarScore.student_id,
        PillarScore.pillar,
        func.avg(PillarScore.qualitative).label('avg_score')
    ).filter(
        PillarScore.year == current_year,
        PillarScore.week_number >= start_week
    ).group_by(
        PillarScore.student_id, PillarScore.pillar
    ).having(
        func.avg(PillarScore.qualitative) < threshold
    ).all()

    for r in results:
        exists = AlertFlag.query.filter_by(
            student_id=r.student_id,
            pillar=r.pillar,
            alert_type='below_threshold',
            is_resolved=0
        ).first()
        if not exists:
            student = db.session.get(Student, r.student_id)
            if student:
                label = PillarScore.PILLAR_LABELS.get(r.pillar, r.pillar)
                db.session.add(AlertFlag(
                    student_id=r.student_id,
                    pillar=r.pillar,
                    alert_type='below_threshold',
                    message=(f'{student.full_name} ({student.class_ref.display_name}) is '
                             f'below threshold in {label} '
                             f'(avg {r.avg_score:.1f}/5.0 over last 4 weeks)')
                ))

    # 2. Consecutive absence alerts (3+ days)
    cutoff = date.today() - timedelta(days=7)
    all_students = Student.query.filter_by(is_active=1).all()
    for student in all_students:
        recent = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == student.id,
            AttendanceRecord.log_date >= cutoff
        ).order_by(AttendanceRecord.log_date.desc()).all()

        streak = 0
        for rec in recent:
            if rec.status == 'absent':
                streak += 1
            else:
                break

        if streak >= 3:
            exists = AlertFlag.query.filter_by(
                student_id=student.id,
                alert_type='absent_streak',
                is_resolved=0
            ).first()
            if not exists:
                db.session.add(AlertFlag(
                    student_id=student.id,
                    alert_type='absent_streak',
                    message=(f'{student.full_name} ({student.class_ref.display_name}) '
                             f'has been absent for {streak} consecutive school days')
                ))

    db.session.commit()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    today = date.today()
    
    # Expected submissions list
    from app.models import TeacherClassSubject
    mappings = TeacherClassSubject.query.all()
    mapped_teacher_ids = [m.teacher_id for m in mappings]
    legacy_teachers = User.query.filter(
        User.role == 'teacher',
        User.is_active == 1,
        User.assigned_class_id != None,
        ~User.id.in_(mapped_teacher_ids)
    ).all()
    
    expected = []
    for m in mappings:
        if m.teacher.is_active:
            expected.append((m.teacher, m.class_ref, m.subject))
    for lt in legacy_teachers:
        expected.append((lt, lt.assigned_class, 'General'))
        
    total_expected = len(expected)
    submitted_today = TeacherDailyLog.query.filter_by(log_date=today).count()
    submission_rate = round(submitted_today / total_expected * 100, 1) if total_expected else 0

    # Attendance stats
    present_today = AttendanceRecord.query.filter_by(log_date=today, status='present').count()
    total_attendance = AttendanceRecord.query.filter_by(log_date=today).count()
    attendance_rate = round(present_today / total_attendance * 100, 1) if total_attendance else 0

    # Generate alerts
    _generate_alerts()
    active_alerts = AlertFlag.query.filter_by(is_resolved=0).count()
    total_students = Student.query.filter_by(is_active=1).count()
    total_classes = Class.query.count()

    # Recent teacher logs
    recent_logs = db.session.query(TeacherDailyLog, User, Class)\
        .join(User, TeacherDailyLog.teacher_id == User.id)\
        .join(Class, TeacherDailyLog.class_id == Class.id)\
        .filter(TeacherDailyLog.log_date == today)\
        .order_by(TeacherDailyLog.submitted_at.desc()).limit(8).all()

    # Last 7-day submission chart
    week_labels, week_counts = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        cnt = TeacherDailyLog.query.filter_by(log_date=d).count()
        week_labels.append(d.strftime('%a %d'))
        week_counts.append(cnt)

    # Top alerts
    top_alerts = AlertFlag.query.filter_by(is_resolved=0)\
        .order_by(AlertFlag.created_at.desc()).limit(5).all()

    # Pending submissions list for today
    submitted_today_logs = TeacherDailyLog.query.filter_by(log_date=today).all()
    submitted_keys = {(l.teacher_id, l.class_id, l.subject) for l in submitted_today_logs}
    
    pending_teachers = []
    for user, cls, subj in expected:
        if (user.id, cls.id, subj) not in submitted_keys:
            class MockTeacherWrapper:
                def __init__(self, user, cls, subj):
                    self.full_name = f"{user.full_name} ({subj})"
                    self.username = user.username
                    class MockClass:
                        def __init__(self, name):
                            self.display_name = name
                    self.assigned_class = MockClass(cls.display_name)
            pending_teachers.append(MockTeacherWrapper(user, cls, subj))

    return render_template('admin/dashboard.html',
        today=today,
        total_teachers=total_expected,
        submitted_today=submitted_today,
        submission_rate=submission_rate,
        attendance_rate=attendance_rate,
        present_today=present_today,
        total_attendance=total_attendance,
        active_alerts=active_alerts,
        total_students=total_students,
        total_classes=total_classes,
        recent_logs=recent_logs,
        week_labels=week_labels,
        week_counts=week_counts,
        top_alerts=top_alerts,
        pending_teachers=pending_teachers,
    )


def get_syllabus_pace(class_id, subject):
    """
    Calculate progress of syllabus relative to time elapsed in the term.
    """
    today = date.today()
    year = today.year
    
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
        status_label = 'Ahead'
    elif diff < -10:
        status = 'delayed'
        status_label = 'Delayed'
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
# Reports — Daily
# ---------------------------------------------------------------------------
@admin_bp.route('/reports/daily')
@login_required
@admin_required
def reports_daily():
    selected_date_str = request.args.get('date', str(date.today()))
    try:
        selected_date = date.fromisoformat(selected_date_str)
    except ValueError:
        selected_date = date.today()

    # Expected submissions list
    from app.models import TeacherClassSubject
    mappings = TeacherClassSubject.query.all()
    mapped_teacher_ids = [m.teacher_id for m in mappings]
    legacy_teachers = User.query.filter(
        User.role == 'teacher',
        User.is_active == 1,
        User.assigned_class_id != None,
        ~User.id.in_(mapped_teacher_ids)
    ).all()

    expected = []
    for m in mappings:
        if m.teacher.is_active:
            expected.append((m.teacher, m.class_ref, m.subject))
    for lt in legacy_teachers:
        expected.append((lt, lt.assigned_class, 'General'))

    submitted_logs = TeacherDailyLog.query.filter_by(log_date=selected_date).all()
    submitted_map = {(l.teacher_id, l.class_id, l.subject): l for l in submitted_logs}

    logs = []
    missing = []

    for user, cls, subj in expected:
        log = submitted_map.get((user.id, cls.id, subj))
        pace = get_syllabus_pace(cls.id, subj)
        if log:
            logs.append((log, user, cls, subj, pace))
        else:
            missing.append((user, cls, subj))

    logs.sort(key=lambda x: (x[2].grade, x[2].section))
    missing.sort(key=lambda x: (x[1].grade, x[1].section))

    return render_template('admin/reports_daily.html',
        selected_date=selected_date,
        today=date.today(),
        logs=logs,
        missing=missing,
        status_labels=TeacherDailyLog.SYLLABUS_STATUS_LABELS,
    )


# ---------------------------------------------------------------------------
# Reports — Weekly
# ---------------------------------------------------------------------------
@admin_bp.route('/reports/weekly')
@login_required
@admin_required
def reports_weekly():
    # Build 7-day range ending today
    today = date.today()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    teachers = User.query.filter_by(role='teacher', is_active=1)\
                         .order_by(User.full_name).all()

    # heatmap[teacher_id][date_str] = True/False
    heatmap = {}
    for t in teachers:
        heatmap[t.id] = {}
        for d in days:
            log = TeacherDailyLog.query.filter_by(
                teacher_id=t.id, log_date=d
            ).first()
            heatmap[t.id][str(d)] = log is not None

    return render_template('admin/reports_weekly.html',
        teachers=teachers,
        days=days,
        heatmap=heatmap,
        today=today,
    )


# ---------------------------------------------------------------------------
# Reports — Monthly
# ---------------------------------------------------------------------------
@admin_bp.route('/reports/monthly')
@login_required
@admin_required
def reports_monthly():
    # Default: current month
    today = date.today()
    year = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))

    # Weekly pillar averages across all classes for this month
    # ISO weeks that fall in this month
    import calendar
    _, last_day = calendar.monthrange(year, month)
    first_date = date(year, month, 1)
    last_date = date(year, month, last_day)

    weeks_in_month = sorted(set(
        (first_date + timedelta(days=i)).isocalendar()[1]
        for i in range((last_date - first_date).days + 1)
    ))

    pillar_trends = {}
    for pillar in PillarScore.PILLARS:
        weekly_avgs = []
        for wk in weeks_in_month:
            avg = db.session.query(func.avg(PillarScore.qualitative))\
                .filter(
                    PillarScore.pillar == pillar,
                    PillarScore.week_number == wk,
                    PillarScore.year == year
                ).scalar()
            weekly_avgs.append(round(avg, 2) if avg else None)
        pillar_trends[pillar] = weekly_avgs

    # Attendance by week
    attendance_weekly = []
    for wk in weeks_in_month:
        # Approximate week start/end
        first_day_of_week = date.fromisocalendar(year, wk, 1)
        last_day_of_week = date.fromisocalendar(year, wk, 7)
        present = AttendanceRecord.query.filter(
            AttendanceRecord.log_date >= first_day_of_week,
            AttendanceRecord.log_date <= last_day_of_week,
            AttendanceRecord.status == 'present'
        ).count()
        total = AttendanceRecord.query.filter(
            AttendanceRecord.log_date >= first_day_of_week,
            AttendanceRecord.log_date <= last_day_of_week,
        ).count()
        attendance_weekly.append(round(present / total * 100, 1) if total else 0)

    # Months for selector
    months = [(m, datetime(2000, m, 1).strftime('%B')) for m in range(1, 13)]
    years = list(range(today.year - 1, today.year + 2))

    return render_template('admin/reports_monthly.html',
        year=year,
        month=month,
        weeks_in_month=weeks_in_month,
        pillar_trends=pillar_trends,
        pillar_labels=PillarScore.PILLAR_LABELS,
        attendance_weekly=attendance_weekly,
        months=months,
        years=years,
        today=today,
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
@admin_bp.route('/alerts')
@login_required
@admin_required
def alerts():
    _generate_alerts()
    filter_type = request.args.get('type', 'all')
    query = AlertFlag.query.filter_by(is_resolved=0)
    if filter_type != 'all':
        query = query.filter_by(alert_type=filter_type)
    active_alerts = query.order_by(AlertFlag.created_at.desc()).all()
    resolved_alerts = AlertFlag.query.filter_by(is_resolved=1)\
        .order_by(AlertFlag.created_at.desc()).limit(20).all()

    return render_template('admin/alerts.html',
        active_alerts=active_alerts,
        resolved_alerts=resolved_alerts,
        filter_type=filter_type,
        alert_type_labels=AlertFlag.ALERT_TYPE_LABELS,
        alert_type_colors=AlertFlag.ALERT_TYPE_COLORS,
    )


@admin_bp.route('/alerts/<int:alert_id>/resolve', methods=['POST'])
@login_required
@admin_required
def resolve_alert(alert_id):
    alert = AlertFlag.query.get_or_404(alert_id)
    alert.is_resolved = 1
    db.session.commit()
    flash('Alert resolved.', 'success')
    return redirect(url_for('admin.alerts'))


@admin_bp.route('/alerts/<int:alert_id>/intervention', methods=['POST'])
@login_required
def record_intervention(alert_id):
    alert = AlertFlag.query.get_or_404(alert_id)
    action_tag = request.form.get('action_tag', '').strip()
    action_note = request.form.get('action_taken', '').strip()

    alert.action_tag = action_tag or 'Remedial Intervention'
    alert.action_taken = action_note or action_tag
    alert.action_by = current_user.id
    alert.action_at = datetime.utcnow()

    if request.form.get('resolve') == '1':
        alert.is_resolved = 1

    db.session.commit()
    flash(f'Remedial action recorded for {alert.student.full_name}: {alert.action_tag}', 'success')

    next_page = request.referrer or url_for('admin.alerts')
    return redirect(next_page)


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    classes = Class.query.order_by(Class.grade, Class.section).all()
    return render_template('admin/users.html', teachers=teachers, classes=classes)


@admin_bp.route('/users/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'teacher')
    class_id = request.form.get('assigned_class_id') or None

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists.', 'danger')
        return redirect(url_for('admin.users'))

    user = User(username=username, full_name=full_name, role=role,
                assigned_class_id=int(class_id) if class_id else None)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f'Account created for {full_name}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    classes = Class.query.order_by(Class.grade, Class.section).all()

    if request.method == 'POST':
        user.full_name = request.form.get('full_name', user.full_name).strip()
        user.role = request.form.get('role', user.role)
        class_id = request.form.get('assigned_class_id') or None
        user.assigned_class_id = int(class_id) if class_id else None
        user.is_active = 1 if request.form.get('is_active') else 0
        new_pw = request.form.get('new_password', '')
        if new_pw:
            user.set_password(new_pw)
        db.session.commit()
        flash(f'Updated {user.full_name} successfully.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/edit_user.html', user=user, classes=classes)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = 0 if user.is_active else 1
    db.session.commit()
    state = 'activated' if user.is_active else 'deactivated'
    flash(f'{user.full_name} has been {state}.', 'info')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/mappings/add', methods=['POST'])
@login_required
@admin_required
def add_user_mapping(user_id):
    from app.models import TeacherClassSubject
    class_id = request.form.get('class_id', type=int)
    subject = request.form.get('subject', '').strip()
    
    if not class_id or not subject:
        flash('Class and Subject are required.', 'danger')
        return redirect(url_for('admin.edit_user', user_id=user_id))
        
    exists = TeacherClassSubject.query.filter_by(
        teacher_id=user_id, class_id=class_id, subject=subject
    ).first()
    
    if exists:
        flash('This mapping already exists.', 'warning')
    else:
        mapping = TeacherClassSubject(teacher_id=user_id, class_id=class_id, subject=subject)
        db.session.add(mapping)
        db.session.commit()
        flash('Class-Subject mapping added.', 'success')
        
    return redirect(url_for('admin.edit_user', user_id=user_id))


@admin_bp.route('/mappings/<int:mapping_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user_mapping(mapping_id):
    from app.models import TeacherClassSubject
    mapping = TeacherClassSubject.query.get_or_404(mapping_id)
    user_id = mapping.teacher_id
    db.session.delete(mapping)
    db.session.commit()
    flash('Class-Subject mapping removed.', 'success')
    return redirect(url_for('admin.edit_user', user_id=user_id))


# ---------------------------------------------------------------------------
# Class Management
# ---------------------------------------------------------------------------
@admin_bp.route('/classes')
@login_required
@admin_required
def classes():
    all_classes = Class.query.order_by(Class.grade, Class.section).all()
    academic_year = current_app.config['ACADEMIC_YEAR']
    return render_template('admin/classes.html',
        all_classes=all_classes,
        academic_year=academic_year,
    )


@admin_bp.route('/classes/add', methods=['POST'])
@login_required
@admin_required
def add_class():
    grade = int(request.form.get('grade', 1))
    section = request.form.get('section', 'A').upper()
    academic_year = current_app.config['ACADEMIC_YEAR']

    if Class.query.filter_by(grade=grade, section=section, academic_year=academic_year).first():
        flash(f'Class {grade}-{section} already exists.', 'warning')
    else:
        cls = Class(grade=grade, section=section, academic_year=academic_year)
        db.session.add(cls)
        db.session.commit()
        flash(f'Class {grade}-{section} created.', 'success')
    return redirect(url_for('admin.classes'))


# ---------------------------------------------------------------------------
# Student Management
# ---------------------------------------------------------------------------
@admin_bp.route('/students')
@login_required
@admin_required
def students():
    class_filter = request.args.get('class_id', type=int)
    query = Student.query.filter_by(is_active=1)
    if class_filter:
        query = query.filter_by(class_id=class_filter)
    all_students = query.join(Class).order_by(Class.grade, Class.section,
                                               Student.roll_number).all()
    all_classes = Class.query.order_by(Class.grade, Class.section).all()

    return render_template('admin/students.html',
        students=all_students,
        classes=all_classes,
        class_filter=class_filter,
    )


@admin_bp.route('/students/add', methods=['POST'])
@login_required
@admin_required
def add_student():
    roll = request.form.get('roll_number', '').strip()
    name = request.form.get('full_name', '').strip()
    class_id = int(request.form.get('class_id'))
    contact = request.form.get('parent_contact', '').strip()

    if Student.query.filter_by(roll_number=roll, class_id=class_id).first():
        flash(f'Roll number {roll} already exists in this class.', 'warning')
    else:
        student = Student(roll_number=roll, full_name=name,
                          class_id=class_id, parent_contact=contact)
        db.session.add(student)
        db.session.commit()
        flash(f'Student {name} added successfully.', 'success')
    return redirect(url_for('admin.students'))


def _promote_single_class(cls, target_year):
    """
    Helper function to promote a single class section to the next grade level.
    Nursery (-3) -> LKG (-2) -> UKG (-1) -> Class 1 (1) -> ... -> Class 10 (10) -> Graduated
    """
    order = Class.GRADE_ORDER
    if cls.grade in order:
        idx = order.index(cls.grade)
        if idx < len(order) - 1:
            next_grade = order[idx + 1]
        else:
            next_grade = None  # Class 10th graduated
    else:
        next_grade = None

    active_students = Student.query.filter_by(class_id=cls.id, is_active=1).all()
    if not active_students:
        return 0, "No Active Students"

    if next_grade is None:
        for s in active_students:
            s.is_active = 0
        db.session.commit()
        return len(active_students), "Graduated"
    else:
        target_cls = Class.query.filter_by(
            grade=next_grade,
            section=cls.section,
            academic_year=target_year
        ).first()
        if not target_cls:
            target_cls = Class(
                grade=next_grade,
                section=cls.section,
                academic_year=target_year
            )
            db.session.add(target_cls)
            db.session.flush()

        count = len(active_students)
        for s in active_students:
            s.class_id = target_cls.id
        db.session.commit()
        return count, target_cls.display_name


@admin_bp.route('/promotion', methods=['GET'])
@login_required
@admin_required
def promotion():
    academic_year = current_app.config['ACADEMIC_YEAR']
    try:
        y1, y2 = academic_year.split('-')
        next_y1 = str(int(y1) + 1)
        next_y2 = str(int(y2) + 1).zfill(2) if len(y2) == 2 else str(int(y2) + 1)
        target_year = f"{next_y1}-{next_y2}"
    except Exception:
        target_year = "2026-27"

    all_classes = Class.query.filter_by(academic_year=academic_year)\
                             .order_by(Class.grade, Class.section).all()

    class_promotions = []
    order = Class.GRADE_ORDER
    for cls in all_classes:
        student_cnt = Student.query.filter_by(class_id=cls.id, is_active=1).count()
        if cls.grade in order:
            idx = order.index(cls.grade)
            if idx < len(order) - 1:
                next_g = order[idx + 1]
                next_label = f"{Class.GRADE_MAP.get(next_g, next_g)}-{cls.section} ({target_year})"
            else:
                next_label = "Graduated (Inactive)"
        else:
            next_label = "Unknown"
        class_promotions.append((cls, next_label, student_cnt))

    return render_template('admin/promotion.html',
        target_year=target_year,
        class_promotions=class_promotions,
    )


@admin_bp.route('/promotion/execute', methods=['POST'])
@login_required
@admin_required
def execute_promotion():
    target_year = request.form.get('target_year', '').strip() or '2026-27'
    class_id_param = request.form.get('class_id', 'all')

    academic_year = current_app.config['ACADEMIC_YEAR']

    if class_id_param == 'all':
        classes_to_promote = Class.query.filter_by(academic_year=academic_year).all()
        total_students = 0
        for cls in classes_to_promote:
            cnt, _ = _promote_single_class(cls, target_year)
            total_students += cnt
        flash(f'Bulk promotion complete! Promoted {total_students} students across {len(classes_to_promote)} class sections for {target_year}.', 'success')
    else:
        cls = Class.query.get_or_404(int(class_id_param))
        cnt, next_name = _promote_single_class(cls, target_year)
        flash(f'Promoted {cnt} students of {cls.display_name} to {next_name} for session {target_year}.', 'success')

    return redirect(url_for('admin.promotion'))


@admin_bp.route('/students/<int:student_id>')
@login_required
@admin_required
def student_profile(student_id):
    student = Student.query.get_or_404(student_id)
    selected_subject = request.args.get('subject', 'All')

    from app.models import TeacherClassSubject
    subjects_query = db.session.query(TeacherClassSubject.subject)\
                               .filter_by(class_id=student.class_id).distinct().all()
    available_subjects = [s[0] for s in subjects_query]
    if 'General' not in available_subjects:
        available_subjects.append('General')

    # Pillar scores history (last 8 weeks)
    now = datetime.now()
    cw = now.isocalendar()[1]
    cy = now.year
    start_wk = max(1, cw - 7)

    pillar_history = {}
    for pillar in PillarScore.PILLARS:
        q = PillarScore.query.filter(
            PillarScore.student_id == student_id,
            PillarScore.pillar == pillar,
            PillarScore.year == cy,
            PillarScore.week_number >= start_wk
        )
        if selected_subject != 'All':
            q = q.filter(PillarScore.subject == selected_subject)
        scores = q.order_by(PillarScore.week_number).all()
        pillar_history[pillar] = scores

    # Attendance summary (last 30 days)
    thirty_days_ago = date.today() - timedelta(days=30)
    attendance_records = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student_id,
        AttendanceRecord.log_date >= thirty_days_ago
    ).order_by(AttendanceRecord.log_date.desc()).all()

    present_count = sum(1 for r in attendance_records if r.status == 'present')
    absent_count = sum(1 for r in attendance_records if r.status == 'absent')
    late_count = sum(1 for r in attendance_records if r.status == 'late')

    # Active alerts
    active_alerts = AlertFlag.query.filter_by(
        student_id=student_id, is_resolved=0
    ).order_by(AlertFlag.created_at.desc()).all()

    # Current week radar data
    radar_data = {}
    for pillar in PillarScore.PILLARS:
        q = PillarScore.query.filter_by(
            student_id=student_id, pillar=pillar,
            week_number=cw, year=cy
        )
        if selected_subject != 'All':
            q = q.filter_by(subject=selected_subject)
        score = q.first()
        radar_data[pillar] = score.qualitative if score else 0

    return render_template('admin/student_profile.html',
        student=student,
        selected_subject=selected_subject,
        available_subjects=available_subjects,
        pillar_history=pillar_history,
        pillar_labels=PillarScore.PILLAR_LABELS,
        pillar_icons=PillarScore.PILLAR_ICONS,
        qualitative_labels=PillarScore.QUALITATIVE_LABELS,
        attendance_records=attendance_records,
        present_count=present_count,
        absent_count=absent_count,
        late_count=late_count,
        active_alerts=active_alerts,
        alert_labels=AlertFlag.ALERT_TYPE_LABELS,
        radar_data=radar_data,
        weeks=list(range(start_wk, cw + 1)),
    )

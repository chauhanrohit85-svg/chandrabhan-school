"""
Director / Super-Admin routes for executive management overview, compliance audits, and physical notebook inspection sheets.
Exclusively accessible to users with role='director'.
"""
from datetime import date, datetime, timedelta
from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from app.director import director_bp
from app.auth.routes import director_required
from app.models import (User, Class, Student, TeacherDailyLog, AttendanceRecord,
                        PillarScore, AlertFlag, TeacherClassSubject)
from app.extensions import db


@director_bp.route('/dashboard')
@login_required
@director_required
def dashboard():
    today = date.today()
    academic_year = current_app.config['ACADEMIC_YEAR']

    total_students = Student.query.filter_by(is_active=1).count()
    total_classes = Class.query.filter_by(academic_year=academic_year).count()
    total_teachers = User.query.filter_by(role='teacher', is_active=1).count()

    # Active alerts & overdue interventions (>7 days without action)
    active_alerts = AlertFlag.query.filter_by(is_resolved=0).all()
    overdue_alerts = [a for a in active_alerts if a.is_overdue_intervention]

    # Daily submission stats for today
    submitted_logs_count = TeacherDailyLog.query.filter_by(log_date=today).count()

    # Compliance calculation (last 7 days)
    seven_days_ago = today - timedelta(days=6)
    expected_daily_logs = total_teachers * 7
    actual_daily_logs = TeacherDailyLog.query.filter(TeacherDailyLog.log_date >= seven_days_ago).count()
    compliance_rate = round((actual_daily_logs / expected_daily_logs * 100), 1) if expected_daily_logs else 0

    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    engine_name = getattr(db.engine, 'name', '') if hasattr(db, 'engine') else ''
    if 'postgresql' in db_uri or 'postgres' in engine_name:
        db_backend = "PostgreSQL (Neon Cloud Vault)"
        db_status = "Permanent Cloud Vault Active"
    else:
        db_backend = "SQLite (Local Dev Storage)"
        db_status = "Local Standalone Mode"



    return render_template('director/dashboard.html',
        today=today,
        total_students=total_students,
        total_classes=total_classes,
        total_teachers=total_teachers,
        active_alerts_count=len(active_alerts),
        overdue_alerts=overdue_alerts,
        submitted_logs_count=submitted_logs_count,
        compliance_rate=compliance_rate,
        db_backend=db_backend,
        db_status=db_status,
        academic_year=academic_year,
    )


@director_bp.route('/compliance')
@login_required
@director_required
def compliance():
    selected_date_str = request.args.get('date', str(date.today()))
    try:
        selected_date = date.fromisoformat(selected_date_str)
    except ValueError:
        selected_date = date.today()

    teachers = User.query.filter(User.role.in_(['teacher', 'admin']), User.is_active == 1)\
                         .order_by(User.role.desc(), User.full_name).all()

    teacher_audit_list = []
    for t in teachers:
        logs = TeacherDailyLog.query.filter_by(teacher_id=t.id, log_date=selected_date).all()
        attendance_marked = AttendanceRecord.query.filter_by(marked_by=t.id, log_date=selected_date).count()

        timestamps = [l.submitted_at for l in logs if l.submitted_at is not None]
        latest_timestamp = max(timestamps) if timestamps else None

        status_flag = 'on_time' if logs else 'missed'

        teacher_audit_list.append({
            'user': t,
            'logs': logs,
            'attendance_count': attendance_marked,
            'latest_timestamp': latest_timestamp,
            'status': status_flag,
        })

    return render_template('director/compliance.html',
        selected_date=selected_date,
        today=date.today(),
        teacher_audit_list=teacher_audit_list,
    )


@director_bp.route('/inspection')
@login_required
@director_required
def inspection():
    """
    Generates a printable Physical Inspection Sheet for school visits.
    Groups weak/flagged students alongside their remedial action logs.
    """
    academic_year = current_app.config['ACADEMIC_YEAR']

    active_alerts = AlertFlag.query.filter_by(is_resolved=0).all()

    grouped_inspection = {}
    for alert in active_alerts:
        if not alert.student or not alert.student.is_active:
            continue
        cls_name = alert.student.class_ref.display_name if alert.student.class_ref else 'General'
        if cls_name not in grouped_inspection:
            grouped_inspection[cls_name] = []
        grouped_inspection[cls_name].append({
            'student': alert.student,
            'cls': alert.student.class_ref,
            'alert': alert,
        })

    return render_template('director/inspection.html',
        today=date.today(),
        grouped_inspection=grouped_inspection,
        intervention_tags=AlertFlag.INTERVENTION_TAGS,
    )


# ---------------------------------------------------------------------------
# Backup & Database Export / Restore
# ---------------------------------------------------------------------------
import json
from flask import Response

def _serialize_model_instance(inst):
    data = {}
    for col in inst.__table__.columns:
        val = getattr(inst, col.name)
        if isinstance(val, (datetime, date)):
            data[col.name] = val.isoformat()
        else:
            data[col.name] = val
    return data


@director_bp.route('/backup')
@login_required
@director_required
def backup():
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    engine_name = getattr(db.engine, 'name', '') if hasattr(db, 'engine') else ''
    if 'postgresql' in db_uri or 'postgres' in engine_name:
        db_backend = "PostgreSQL (Neon Cloud Vault)"
    else:
        db_backend = "SQLite (Local Dev Storage)"


    stats = {
        'users': User.query.count(),
        'classes': Class.query.count(),
        'students': Student.query.count(),
        'teacher_mappings': TeacherClassSubject.query.count(),
        'daily_logs': TeacherDailyLog.query.count(),
        'attendance_records': AttendanceRecord.query.count(),
        'pillar_scores': PillarScore.query.count(),
        'alerts': AlertFlag.query.count(),
    }

    return render_template('director/backup.html',
        db_backend=db_backend,
        db_uri=db_uri,
        stats=stats,
    )


@director_bp.route('/backup/export')
@login_required
@director_required
def backup_export():
    backup_data = {
        'version': '2.0',
        'school_name': current_app.config['SCHOOL_NAME'],
        'exported_at': datetime.utcnow().isoformat(),
        'exported_by': current_user.username,
        'tables': {
            'users': [_serialize_model_instance(u) for u in User.query.all()],
            'classes': [_serialize_model_instance(c) for c in Class.query.all()],
            'students': [_serialize_model_instance(s) for s in Student.query.all()],
            'teacher_class_subjects': [_serialize_model_instance(m) for m in TeacherClassSubject.query.all()],
            'daily_logs': [_serialize_model_instance(l) for l in TeacherDailyLog.query.all()],
            'attendance_records': [_serialize_model_instance(a) for a in AttendanceRecord.query.all()],
            'pillar_scores': [_serialize_model_instance(p) for p in PillarScore.query.all()],
            'alert_flags': [_serialize_model_instance(f) for f in AlertFlag.query.all()],
        }
    }

    json_str = json.dumps(backup_data, indent=2)
    filename = f"chandrabhan_school_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    return Response(
        json_str,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@director_bp.route('/backup/restore', methods=['POST'])
@login_required
@director_required
def backup_restore():
    file = request.files.get('backup_file')
    if not file or not file.filename.endswith('.json'):
        flash('Invalid backup file. Please upload a valid JSON backup file.', 'danger')
        return redirect(url_for('director.backup'))

    try:
        content = json.loads(file.read().decode('utf-8'))
        tables = content.get('tables', {})

        # Restore Users
        for u_data in tables.get('users', []):
            existing = db.session.get(User, u_data['id']) or User.query.filter_by(username=u_data['username']).first()
            if existing:
                existing.full_name = u_data.get('full_name', existing.full_name)
                existing.role = u_data.get('role', existing.role)
                existing.assigned_class_id = u_data.get('assigned_class_id', existing.assigned_class_id)
                existing.is_active = u_data.get('is_active', existing.is_active)
            else:
                user = User(
                    id=u_data['id'],
                    username=u_data['username'],
                    password_hash=u_data['password_hash'],
                    full_name=u_data['full_name'],
                    role=u_data['role'],
                    assigned_class_id=u_data.get('assigned_class_id'),
                    is_active=u_data.get('is_active', 1)
                )
                db.session.add(user)

        # Restore Classes
        for c_data in tables.get('classes', []):
            existing = db.session.get(Class, c_data['id'])
            if not existing:
                cls = Class(
                    id=c_data['id'],
                    grade=c_data['grade'],
                    section=c_data['section'],
                    academic_year=c_data['academic_year']
                )
                db.session.add(cls)

        # Restore Students
        for s_data in tables.get('students', []):
            existing = db.session.get(Student, s_data['id'])
            if existing:
                existing.full_name = s_data.get('full_name', existing.full_name)
                existing.roll_number = s_data.get('roll_number', existing.roll_number)
                existing.parent_contact = s_data.get('parent_contact', existing.parent_contact)
                existing.is_active = s_data.get('is_active', existing.is_active)
            else:
                s = Student(
                    id=s_data['id'],
                    roll_number=s_data['roll_number'],
                    full_name=s_data['full_name'],
                    class_id=s_data['class_id'],
                    parent_contact=s_data.get('parent_contact'),
                    is_active=s_data.get('is_active', 1)
                )
                db.session.add(s)

        # Restore Daily Logs
        for l_data in tables.get('daily_logs', []):
            existing = db.session.get(TeacherDailyLog, l_data['id'])
            if not existing:
                log_d = date.fromisoformat(l_data['log_date']) if isinstance(l_data['log_date'], str) else l_data['log_date']
                sub_d = datetime.fromisoformat(l_data['submitted_at']) if l_data.get('submitted_at') else None
                log = TeacherDailyLog(
                    id=l_data['id'],
                    teacher_id=l_data['teacher_id'],
                    class_id=l_data['class_id'],
                    subject=l_data['subject'],
                    log_date=log_d,
                    topic_taught=l_data.get('topic_taught', ''),
                    lesson_status=l_data.get('lesson_status', 'Concept Taught'),
                    remarks=l_data.get('remarks'),
                    media_attachment_base64=l_data.get('media_attachment_base64'),
                    submitted_at=sub_d
                )
                db.session.add(log)

        # Restore Attendance Records
        for a_data in tables.get('attendance_records', []):
            existing = db.session.get(AttendanceRecord, a_data['id'])
            if not existing:
                a_date = date.fromisoformat(a_data['log_date']) if isinstance(a_data['log_date'], str) else a_data['log_date']
                rec = AttendanceRecord(
                    id=a_data['id'],
                    student_id=a_data['student_id'],
                    log_date=a_date,
                    status=a_data['status'],
                    marked_by=a_data['marked_by']
                )
                db.session.add(rec)

        # Restore Pillar Scores
        for p_data in tables.get('pillar_scores', []):
            existing = db.session.get(PillarScore, p_data['id'])
            if not existing:
                score = PillarScore(
                    id=p_data['id'],
                    student_id=p_data['student_id'],
                    pillar=p_data['pillar'],
                    subject=p_data.get('subject', 'General'),
                    week_number=p_data['week_number'],
                    year=p_data['year'],
                    qualitative=p_data.get('qualitative', 3),
                    quantitative_score=p_data.get('quantitative_score', 60.0),
                    remarks=p_data.get('remarks'),
                    photo_base64=p_data.get('photo_base64'),
                    recorded_by=p_data['recorded_by']
                )
                db.session.add(score)

        db.session.commit()
        flash('Database successfully restored from backup file!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring database: {str(e)}', 'danger')

    return redirect(url_for('director.backup'))

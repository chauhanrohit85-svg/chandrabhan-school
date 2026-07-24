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

    return render_template('director/dashboard.html',
        today=today,
        total_students=total_students,
        total_classes=total_classes,
        total_teachers=total_teachers,
        active_alerts_count=len(active_alerts),
        overdue_alerts=overdue_alerts,
        submitted_logs_count=submitted_logs_count,
        compliance_rate=compliance_rate,
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

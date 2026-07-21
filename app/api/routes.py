"""
Offline sync API routes.
Accepts JSON payloads from autosave.js/sync.js to batch-upsert local data.
"""
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import date, datetime
from app.api import api_bp
from app.extensions import db
from app.models import TeacherDailyLog, AttendanceRecord, PillarScore


@api_bp.route('/health', methods=['GET'])
def health():
    """Lightweight endpoint for connectivity check by sync.js."""
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})


@api_bp.route('/sync/log', methods=['POST'])
@login_required
def sync_log():
    """Sync a daily log saved offline."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No JSON payload'}), 400

    try:
        log_date = date.fromisoformat(data.get('log_date', str(date.today())))
        subject = data.get('subject', 'General')
        existing = TeacherDailyLog.query.filter_by(
            teacher_id=current_user.id,
            class_id=data['class_id'],
            subject=subject,
            log_date=log_date
        ).first()

        if existing:
            existing.lesson_completed = int(data.get('lesson_completed', 0))
            existing.syllabus_topic = data.get('syllabus_topic', '')
            existing.syllabus_status = data.get('syllabus_status', 'on_track')
            existing.homework_assigned = int(data.get('homework_assigned', 0))
            existing.remarks = data.get('remarks', '')
            if data.get('photo_base64'):
                existing.photo_base64 = data.get('photo_base64')
            existing.submitted_at = datetime.utcnow()
        else:
            log = TeacherDailyLog(
                teacher_id=current_user.id,
                class_id=data['class_id'],
                log_date=log_date,
                lesson_completed=int(data.get('lesson_completed', 0)),
                syllabus_topic=data.get('syllabus_topic', ''),
                syllabus_status=data.get('syllabus_status', 'on_track'),
                subject=subject,
                photo_base64=data.get('photo_base64'),
                homework_assigned=int(data.get('homework_assigned', 0)),
                remarks=data.get('remarks', '')
            )
            db.session.add(log)

        db.session.commit()
        return jsonify({'status': 'synced'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Sync log error: {e}')
        return jsonify({'error': str(e)}), 500


@api_bp.route('/sync/attendance', methods=['POST'])
@login_required
def sync_attendance():
    """Sync attendance records saved offline. Accepts array of records."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Expected JSON array'}), 400

    synced = 0
    try:
        for record in data:
            log_date = date.fromisoformat(record.get('log_date', str(date.today())))
            existing = AttendanceRecord.query.filter_by(
                student_id=record['student_id'],
                log_date=log_date
            ).first()

            if existing:
                existing.status = record.get('status', 'present')
                existing.marked_by = current_user.id
            else:
                att = AttendanceRecord(
                    student_id=record['student_id'],
                    log_date=log_date,
                    status=record.get('status', 'present'),
                    marked_by=current_user.id
                )
                db.session.add(att)
            synced += 1

        db.session.commit()
        return jsonify({'status': 'synced', 'count': synced}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Sync attendance error: {e}')
        return jsonify({'error': str(e)}), 500


@api_bp.route('/sync/pillars', methods=['POST'])
@login_required
def sync_pillars():
    """Sync pillar scores saved offline. Accepts array of score objects."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Expected JSON array'}), 400

    synced = 0
    valid_pillars = PillarScore.PILLARS
    try:
        for item in data:
            if item.get('pillar') not in valid_pillars:
                continue

            subject = item.get('subject', 'General')
            existing = PillarScore.query.filter_by(
                student_id=item['student_id'],
                pillar=item['pillar'],
                subject=subject,
                week_number=item['week_number'],
                year=item['year']
            ).first()

            if existing:
                existing.qualitative = int(item.get('qualitative', 3))
                existing.quantitative_score = float(item.get('quantitative_score', 0))
                existing.remarks = item.get('remarks')
                if item.get('photo_base64'):
                    existing.photo_base64 = item.get('photo_base64')
                existing.recorded_by = current_user.id
                existing.recorded_at = datetime.utcnow()
            else:
                score = PillarScore(
                    student_id=item['student_id'],
                    pillar=item['pillar'],
                    subject=subject,
                    week_number=item['week_number'],
                    year=item['year'],
                    qualitative=int(item.get('qualitative', 3)),
                    quantitative_score=float(item.get('quantitative_score', 0)),
                    remarks=item.get('remarks'),
                    photo_base64=item.get('photo_base64'),
                    recorded_by=current_user.id
                )
                db.session.add(score)
            synced += 1

        db.session.commit()
        return jsonify({'status': 'synced', 'count': synced}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Sync pillars error: {e}')
        return jsonify({'error': str(e)}), 500

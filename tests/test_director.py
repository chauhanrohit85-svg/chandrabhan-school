"""
Tests for Director / Super-Admin Portal:
- Authentication & Role-Based Access Restrictions
- Compliance Audit Page
- Weak Student Intervention Logging
- Physical Inspection Sheet Generator
"""
import pytest
from datetime import datetime, timedelta
from app.models import User, Student, AlertFlag, Class


@pytest.fixture()
def director_client(app):
    """Authenticated Director client fixture."""
    with app.app_context():
        from app.extensions import db
        d = User.query.filter_by(username='director').first()
        if not d:
            d = User(username='director', full_name='Director Admin', role='director', is_active=1)
            d.set_password('director123')
            db.session.add(d)
            db.session.commit()
        else:
            d.is_active = 1
            d.set_password('director123')
            db.session.commit()

    c = app.test_client()
    c.post('/auth/login', data={'username': 'director', 'password': 'director123'}, follow_redirects=True)
    return c





def test_director_login_success(director_client):
    """Director login redirects to Director Dashboard."""
    resp = director_client.get('/director/dashboard', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Super-Admin Executive Controls' in resp.data or b'Director' in resp.data


def test_teacher_blocked_from_director_dashboard(teacher_client):
    """Teacher cannot access Director Dashboard routes."""
    resp = teacher_client.get('/director/dashboard', follow_redirects=False)
    assert resp.status_code == 302
    assert '/auth/login' in resp.location

    resp_followed = teacher_client.get('/director/dashboard', follow_redirects=True)
    assert b'Super-Admin Executive Controls' not in resp_followed.data


def test_principal_blocked_from_director_dashboard(admin_client):
    """Principal (admin role) cannot access confidential Director Dashboard routes."""
    resp = admin_client.get('/director/dashboard', follow_redirects=False)
    assert resp.status_code == 302
    assert '/auth/login' in resp.location

    resp_followed = admin_client.get('/director/dashboard', follow_redirects=True)
    assert b'Super-Admin Executive Controls' not in resp_followed.data


def test_compliance_audit_page_loads(director_client):
    """Director can load Staff Compliance Audit page."""
    resp = director_client.get('/director/compliance', follow_redirects=True)
    if b'Compliance' not in resp.data:
        print("DEBUG COMPLIANCE RESP STATUS:", resp.status_code)
        print("DEBUG COMPLIANCE RESP DATA:", resp.data[:500])
    assert resp.status_code == 200
    assert b'Compliance' in resp.data or b'Audit' in resp.data or b'Staff' in resp.data


def test_physical_inspection_sheet_generator(director_client):
    """Director can load Physical Inspection Sheet generator page."""
    resp = director_client.get('/director/inspection', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Inspection' in resp.data or b'Physical' in resp.data


def test_remedial_intervention_logging(app, admin_client):
    """Verify logging a remedial intervention tag updates action_tag and action_at."""
    with app.app_context():
        from app.extensions import db
        student = Student.query.first()
        alert = AlertFlag(
            student_id=student.id,
            alert_type='below_threshold',
            message='Test Literacy Alert for Intervention'
        )
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id

    # Post intervention tag
    resp = admin_client.post(f'/admin/alerts/{alert_id}/intervention', data={
        'action_tag': 'Remedial Homework Given',
        'action_taken': 'Assigned 5 extra reading drills.'
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        updated_alert = db.session.get(AlertFlag, alert_id)
        assert updated_alert.action_tag == 'Remedial Homework Given'
        assert updated_alert.action_taken == 'Assigned 5 extra reading drills.'
        assert updated_alert.action_at is not None


def test_overdue_intervention_flag(app):
    """Verify is_overdue_intervention returns True when >7 days without action."""
    with app.app_context():
        from app.extensions import db
        student = Student.query.first()
        eight_days_ago = datetime.utcnow() - timedelta(days=8)

        old_alert = AlertFlag(
            student_id=student.id,
            alert_type='consistent_decline',
            message='Old Alert >7 Days',
            created_at=eight_days_ago
        )
        db.session.add(old_alert)
        db.session.commit()

        assert old_alert.is_overdue_intervention is True


def test_backup_page_loads(director_client):
    """Director can load Backup & Restore management page."""
    resp = director_client.get('/director/backup', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Backup' in resp.data or b'Restore' in resp.data


def test_backup_export(director_client):
    """Director can export full school backup as JSON file."""
    import json
    resp = director_client.get('/director/backup/export')
    assert resp.status_code == 200
    assert resp.content_type == 'application/json'

    data = json.loads(resp.data.decode('utf-8'))
    assert 'tables' in data
    assert 'students' in data['tables']
    assert 'users' in data['tables']


def test_backup_restore(director_client, app):
    """Director can restore database records from JSON backup file."""
    import json, io
    backup_content = {
        'version': '2.0',
        'tables': {
            'students': [{
                'id': 9999,
                'roll_number': '777',
                'full_name': 'Restored Student Test',
                'class_id': 1,
                'parent_contact': '+91 7000000777',
                'is_active': 1
            }]
        }
    }
    json_bytes = json.dumps(backup_content).encode('utf-8')
    data = {
        'backup_file': (io.BytesIO(json_bytes), 'backup_test.json')
    }

    resp = director_client.post('/director/backup/restore', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        restored = Student.query.get(9999)
        assert restored is not None
        assert restored.full_name == 'Restored Student Test'


def test_postgresql_uri_conversion(monkeypatch):
    """Verify postgres:// is converted to postgresql:// in Config._db_uri()."""
    from app.config import Config
    monkeypatch.setenv('DATABASE_URL', 'postgres://user:pass@ep-test.neon.tech/neondb')
    uri = Config._db_uri()
    assert uri.startswith('postgresql://')


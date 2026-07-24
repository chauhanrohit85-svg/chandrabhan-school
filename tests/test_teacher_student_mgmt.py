"""
Tests for Teacher Direct Student Management Permissions.
"""
import pytest
from app.models import Student, User, Class


def test_teacher_can_view_student_roster(teacher_client, app):
    """Logged in teacher can load student roster page."""
    resp = teacher_client.get('/teacher/students', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Student Roster' in resp.data or b'Students' in resp.data or b'Student Management' in resp.data


def test_teacher_can_add_student(teacher_client, app):
    """Teacher can directly add a new student to their class."""
    resp = teacher_client.post('/teacher/students/add', data={
        'roll_number': '888',
        'full_name': 'New Student By Teacher',
        'parent_contact': '+91 9999900000'
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        teacher = User.query.filter_by(username='test_teacher1').first()
        student = Student.query.filter_by(roll_number='888', class_id=teacher.assigned_class_id).first()
        assert student is not None
        assert student.full_name == 'New Student By Teacher'


def test_teacher_can_edit_student(teacher_client, app):
    """Teacher can edit an existing student profile in their assigned class."""
    with app.app_context():
        teacher = User.query.filter_by(username='test_teacher1').first()
        student = Student.query.filter_by(class_id=teacher.assigned_class_id).first()
        student_id = student.id

    resp = teacher_client.post(f'/teacher/students/{student_id}/edit', data={
        'roll_number': '01',
        'full_name': 'Updated Name By Teacher',
        'parent_contact': '+91 8888800000',
        'is_active': 'on'
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        updated_student = Student.query.get(student_id)
        assert updated_student.full_name == 'Updated Name By Teacher'

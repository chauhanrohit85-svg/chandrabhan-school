"""
Tests for Annual Session Bulk Promotion / Class Rollover Logic.
"""
import pytest
from app.models import Class, Student
from app.admin.routes import _promote_single_class


def test_bulk_class_promotion(app):
    """
    Verify single-click promotion rolls over Nursery-A to LKG-A and graduates Class 10th.
    """
    with app.app_context():
        from app.extensions import db
        # 1. Setup Nursery-A (2025-26) with active students
        nursery_a = Class.query.filter_by(grade=-3, section='A', academic_year='2025-26').first()
        if not nursery_a:
            nursery_a = Class(grade=-3, section='A', academic_year='2025-26')
            db.session.add(nursery_a)
            db.session.flush()

        student_nursery = Student(roll_number='01', full_name='Nursery Kid', class_id=nursery_a.id)
        db.session.add(student_nursery)

        # 2. Setup Class 10-A (2025-26) with active students
        class10_a = Class.query.filter_by(grade=10, section='A', academic_year='2025-26').first()
        if not class10_a:
            class10_a = Class(grade=10, section='A', academic_year='2025-26')
            db.session.add(class10_a)
            db.session.flush()

        student_c10 = Student(roll_number='01', full_name='Senior Student', class_id=class10_a.id)
        db.session.add(student_c10)
        db.session.commit()

        # 3. Promote Nursery-A to 2026-27 session
        cnt_promoted, target_name = _promote_single_class(nursery_a, '2026-27')
        assert cnt_promoted == 1
        assert 'LKG-A' in target_name

        # Verify student_nursery is now in LKG-A
        updated_nursery_student = Student.query.get(student_nursery.id)
        assert updated_nursery_student.class_ref.display_name == 'LKG-A'
        assert updated_nursery_student.class_ref.academic_year == '2026-27'

        # 4. Promote Class 10-A to 2026-27 session (Graduation)
        cnt_graduated, grad_name = _promote_single_class(class10_a, '2026-27')
        assert cnt_graduated == 1
        assert grad_name == 'Graduated'

        # Verify senior student is marked inactive (graduated)
        updated_c10_student = Student.query.get(student_c10.id)
        assert updated_c10_student.is_active == 0


def test_admin_promotion_endpoint(admin_client, app):
    """Admin promotion UI route returns HTTP 200."""
    resp = admin_client.get('/admin/promotion', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Promotion' in resp.data or b'Rollover' in resp.data

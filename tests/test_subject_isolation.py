"""
Tests for 5-Pillar Subject Feedback Isolation.
"""
import pytest
from datetime import datetime
from app.models import PillarScore, Student, User


def test_subject_isolation_in_pillar_scores(app):
    """
    Verify that pillar scores and remarks entered under Mathematics NEVER leak into English.
    """
    with app.app_context():
        from app.extensions import db
        teacher = User.query.filter_by(username='test_teacher1').first()
        student = Student.query.first()
        cw = datetime.now().isocalendar()[1]
        cy = datetime.now().year

        # Create score under Mathematics
        math_score = PillarScore(
            student_id=student.id,
            pillar='mathematics',
            subject='Mathematics',
            week_number=cw,
            year=cy,
            qualitative=5,
            quantitative_score=95.0,
            remarks='[Math Concept Clear]',
            recorded_by=teacher.id
        )
        db.session.add(math_score)
        db.session.commit()

        # Query scores for English
        english_scores = PillarScore.query.filter_by(
            student_id=student.id,
            pillar='mathematics',
            subject='English',
            week_number=cw,
            year=cy
        ).all()

        # Must be empty — Math score must not bleed into English
        assert len(english_scores) == 0

        # Query scores for Mathematics
        math_scores = PillarScore.query.filter_by(
            student_id=student.id,
            pillar='mathematics',
            subject='Mathematics',
            week_number=cw,
            year=cy
        ).all()

        assert len(math_scores) == 1
        assert math_scores[0].remarks == '[Math Concept Clear]'

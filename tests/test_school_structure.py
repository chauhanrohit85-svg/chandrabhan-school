"""
Tests for Nursery to Class 10th Section A & B School Structure.
"""
import pytest
from app.models import Class


def test_full_school_structure_creation(app):
    """
    Verify Nursery, LKG, UKG, Class 1-10 with Sections A & B exist or can be created.
    """
    with app.app_context():
        from app.extensions import db
        academic_year = '2025-26'
        grades = [-3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        sections = ['A', 'B']

        for g in grades:
            for sec in sections:
                cls = Class.query.filter_by(grade=g, section=sec, academic_year=academic_year).first()
                if not cls:
                    cls = Class(grade=g, section=sec, academic_year=academic_year)
                    db.session.add(cls)
        db.session.commit()

        # Check total sections (13 grades * 2 sections = 26)
        total_sections = Class.query.filter_by(academic_year=academic_year).count()
        assert total_sections >= 26

        # Check display names
        nursery_a = Class.query.filter_by(grade=-3, section='A', academic_year=academic_year).first()
        assert nursery_a.display_name == 'Nursery-A'

        lkg_b = Class.query.filter_by(grade=-2, section='B', academic_year=academic_year).first()
        assert lkg_b.display_name == 'LKG-B'

        ukg_a = Class.query.filter_by(grade=-1, section='A', academic_year=academic_year).first()
        assert ukg_a.display_name == 'UKG-A'

        c10_b = Class.query.filter_by(grade=10, section='B', academic_year=academic_year).first()
        assert c10_b.display_name == 'Class 10-B'

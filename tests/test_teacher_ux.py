"""
Tests for the low-typing teacher entry screens.

The goal of these screens is that a normal day's data entry needs taps only, so
these tests pin the behaviour that makes that possible: derived percentages,
reusable previous topics, and last week's scores being available to copy.
"""
from datetime import date, timedelta

from app.models import Student, Class, User, PillarScore, TeacherDailyLog


# ---------------------------------------------------------------------------
# Pillar scores: no number needs to be typed
# ---------------------------------------------------------------------------
def test_blank_percent_is_derived_from_the_star_rating(teacher_client, app):
    """
    A star rating implies a percentage, so leaving the % box empty must still
    store a sensible score rather than 0. Typing a number per student per pillar
    was the single largest source of typing on this screen.
    """
    with app.app_context():
        student = Student.query.first()
        student_id = student.id

    week, year = date.today().isocalendar()[1], date.today().isocalendar()[0]

    resp = teacher_client.post('/teacher/pillars/entry', data={
        'week_number': week,
        'year': year,
        f'qual_{student_id}_reading': '4',
        f'quant_{student_id}_reading': '',        # deliberately blank
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        score = PillarScore.query.filter_by(
            student_id=student_id, pillar='reading', week_number=week, year=year
        ).first()
        assert score is not None
        assert score.qualitative == 4
        assert score.quantitative_score == PillarScore.QUALITATIVE_PERCENT[4]


def test_typed_percent_overrides_the_derived_one(teacher_client, app):
    """A teacher who does enter an exact mark keeps it."""
    with app.app_context():
        student_id = Student.query.first().id

    week, year = date.today().isocalendar()[1], date.today().isocalendar()[0]

    teacher_client.post('/teacher/pillars/entry', data={
        'week_number': week,
        'year': year,
        f'qual_{student_id}_writing': '3',
        f'quant_{student_id}_writing': '72.5',
    }, follow_redirects=True)

    with app.app_context():
        score = PillarScore.query.filter_by(
            student_id=student_id, pillar='writing', week_number=week, year=year
        ).first()
        assert score.quantitative_score == 72.5


def test_invalid_percent_falls_back_instead_of_erroring(teacher_client, app):
    """Junk in the % box must not lose the rating the teacher tapped."""
    with app.app_context():
        student_id = Student.query.first().id

    week, year = date.today().isocalendar()[1], date.today().isocalendar()[0]

    resp = teacher_client.post('/teacher/pillars/entry', data={
        'week_number': week,
        'year': year,
        f'qual_{student_id}_reasoning': '5',
        f'quant_{student_id}_reasoning': 'not a number',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        score = PillarScore.query.filter_by(
            student_id=student_id, pillar='reasoning', week_number=week, year=year
        ).first()
        assert score.qualitative == 5
        assert score.quantitative_score == PillarScore.QUALITATIVE_PERCENT[5]


def test_pillar_page_offers_last_week_scores_to_copy(teacher_client, app):
    """
    Last week's ratings are handed to the page so "Copy last week" can prefill
    them. Most students do not change week to week, so this turns a full re-entry
    into adjusting a few outliers.
    """
    with app.app_context():
        from app.extensions import db
        student = Student.query.first()
        teacher = User.query.filter_by(username='test_teacher1').first()
        last_week = date.today() - timedelta(weeks=1)
        iso = last_week.isocalendar()

        existing = PillarScore.query.filter_by(
            student_id=student.id, pillar='reading', subject='General',
            week_number=iso[1], year=iso[0]).first()
        if not existing:
            db.session.add(PillarScore(
                student_id=student.id, pillar='reading', subject='General',
                week_number=iso[1], year=iso[0], qualitative=4,
                quantitative_score=80.0, recorded_by=teacher.id))
            db.session.commit()
        expected_key = f'{student.id}_reading'

    body = teacher_client.get('/teacher/pillars').get_data(as_text=True)
    assert 'data-last-week=' in body
    assert expected_key in body
    assert 'Copy week' in body


def test_pillar_page_has_tap_targets_not_free_text_scores(teacher_client):
    """Scores are radio buttons, and the milestone note is tag-driven."""
    body = teacher_client.get('/teacher/pillars').get_data(as_text=True)
    assert 'type="radio"' in body
    for tag in PillarScore.MILESTONE_TAGS[:3]:
        assert tag in body
    # The remarks field is hidden and filled by tapping tags.
    assert 'type="hidden" name="remarks_' in body


# ---------------------------------------------------------------------------
# Daily log: previous topics come back as one-tap chips
# ---------------------------------------------------------------------------
def test_daily_log_offers_previous_topics(teacher_client, app):
    with app.app_context():
        from app.extensions import db
        teacher = User.query.filter_by(username='test_teacher1').first()
        cls = Class.query.first()
        topic = 'Chapter 7: Photosynthesis'

        if not TeacherDailyLog.query.filter_by(
                teacher_id=teacher.id, class_id=cls.id,
                subject='General', log_date=date.today() - timedelta(days=2)).first():
            db.session.add(TeacherDailyLog(
                teacher_id=teacher.id, class_id=cls.id, subject='General',
                log_date=date.today() - timedelta(days=2),
                syllabus_topic=topic, lesson_completed=1))
            db.session.commit()

    body = teacher_client.get('/teacher/log/daily').get_data(as_text=True)
    assert 'Chapter 7: Photosynthesis' in body, 'previous topic not offered for reuse'
    assert 'Same topic' in body
    assert '<datalist' in body, 'topic autocomplete missing'


def test_daily_log_quick_notes_are_available(teacher_client):
    """Notes are chips, so the free-text box is optional."""
    body = teacher_client.get('/teacher/log/daily').get_data(as_text=True)
    for note in TeacherDailyLog.QUICK_NOTES[:3]:
        assert note in body


def test_daily_log_still_saves(teacher_client, app):
    """The rebuilt form posts the same fields the route expects."""
    resp = teacher_client.post('/teacher/log/daily', data={
        'lesson_completed': 'on',
        'syllabus_topic': 'Chapter 9: Algebra basics',
        'syllabus_status': 'on_track',
        'homework_assigned': 'on',
        'remarks': 'Revision done',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        log = TeacherDailyLog.query.filter_by(
            log_date=date.today(), syllabus_topic='Chapter 9: Algebra basics').first()
        assert log is not None
        assert log.lesson_completed == 1
        assert log.homework_assigned == 1


# ---------------------------------------------------------------------------
# Student profile charts
# ---------------------------------------------------------------------------
def test_student_profile_exposes_chart_data(admin_client, app):
    with app.app_context():
        student_id = Student.query.first().id

    body = admin_client.get(f'/admin/students/{student_id}').get_data(as_text=True)

    # Trend line, radar and attendance ring all present.
    assert 'id="trend-chart"' in body
    assert 'id="student-radar"' in body
    assert 'data-series=' in body

    # Plain-language explanations, not just numbers.
    assert 'How is' in body
    assert 'Reading this:' in body


def test_student_profile_handles_a_student_with_no_scores(admin_client, app):
    """A brand new student must not break the page or show a misleading zero."""
    with app.app_context():
        from app.extensions import db
        cls = Class.query.first()
        fresh = Student(roll_number='ZZ99', full_name='Brand New Student', class_id=cls.id)
        db.session.add(fresh)
        db.session.commit()
        fresh_id = fresh.id

    resp = admin_client.get(f'/admin/students/{fresh_id}')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'No scores yet' in body
    assert 'Not scored' in body

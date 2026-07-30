"""
Tests for the bulk import of teachers and students.

The source is nearly always a hand-typed register, so the parser has to cope
with inconsistent class names and honorifics, and — more importantly — must
never write anything the user has not seen in the preview first.
"""
import pytest

from app.admin.importer import (
    normalise_class, clean_name, make_username,
    preview_teachers, commit_teachers,
    preview_students, commit_students,
)
from app.models import User, Class, Student, TeacherClassSubject


@pytest.fixture(autouse=True)
def full_class_structure(app):
    """
    The shared fixtures seed a single class; importing needs the real timetable.
    Creates every Nursery..Class 10 section that is missing, once per session.
    """
    with app.app_context():
        from app.extensions import db
        for grade in Class.GRADE_ORDER:
            for section in ('A', 'B'):
                exists = Class.query.filter_by(
                    grade=grade, section=section, academic_year='2026-27').first()
                if not exists:
                    db.session.add(Class(grade=grade, section=section,
                                         academic_year='2026-27'))
        db.session.commit()


# ---------------------------------------------------------------------------
# Class name parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('text, expected', [
    ('Nursery-A', (-3, 'A')),
    ('nursery', (-3, 'A')),
    ('LKG B', (-2, 'B')),
    ('lkg-a', (-2, 'A')),
    ('UKG-B', (-1, 'B')),
    ('Class 1-A', (1, 'A')),
    ('1st A', (1, 'A')),
    ('1a', (1, 'A')),
    ('1-B', (1, 'B')),
    ('Class 10', (10, 'A')),
    ('10th B', (10, 'B')),
    ('  class   7   a  ', (7, 'A')),
    ('Std 5-B', (5, 'B')),
])
def test_class_names_are_read_loosely(text, expected):
    assert normalise_class(text) == expected


@pytest.mark.parametrize('text', ['', None, 'nonsense', 'Class 15-A', 'Class 0'])
def test_unreadable_class_names_are_rejected_not_guessed(text):
    assert normalise_class(text) is None


def test_honorifics_are_kept_in_the_name_but_dropped_from_the_username():
    """The school refers to staff as "X Ma'am"; the login should still be short."""
    assert clean_name("  ruchi   ma'am ") == "Ruchi Ma'am"
    assert make_username("Ruchi Ma'am", set()) == 'ruchi'
    assert make_username('Sunil Sir', set()) == 'sunil'


def test_usernames_do_not_collide():
    taken = set()
    first = make_username('Deepika Parmar Ma\'am', taken)
    second = make_username('Deepika Sharma Ma\'am', taken)
    third = make_username('Deepika Parmar Ma\'am', taken)
    assert first == 'deepika.parmar'
    assert second == 'deepika.sharma'
    assert third != first


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------
def test_preview_writes_nothing(app):
    """The whole point of a preview is that it is safe to run."""
    with app.app_context():
        before = User.query.count()
        preview_teachers("Preview Only Ma'am, Class 5-A", '2026-27')
        assert User.query.count() == before


def test_teacher_import_creates_accounts_and_links_classes(app):
    with app.app_context():
        listing = "Import One Ma'am, Class 5-A, English"
        entries = preview_teachers(listing, '2026-27')
        assert entries[0]['status'] == 'create'
        assert entries[0]['class_name'] == 'Class 5-A'

        created, linked, skipped = commit_teachers(listing, '2026-27', 'startingpw1')
        assert (created, linked, skipped) == (1, 1, 0)

        teacher = User.query.filter_by(full_name="Import One Ma'am").first()
        assert teacher is not None
        assert teacher.role == 'teacher'
        assert teacher.check_password('startingpw1')

        mapping = TeacherClassSubject.query.filter_by(teacher_id=teacher.id).first()
        assert mapping.subject == 'English'


def test_one_teacher_across_several_classes_gets_a_single_account(app):
    """A teacher listed on three rows must not become three logins."""
    with app.app_context():
        listing = (
            "Multi Class Sir, Class 4-A, English\n"
            "Multi Class Sir, Class 5-A, English\n"
            "Multi Class Sir, Class 4-A, Reasoning\n"
        )
        created, linked, _ = commit_teachers(listing, '2026-27', 'startingpw1')
        assert created == 1
        assert linked == 3

        accounts = User.query.filter_by(full_name='Multi Class Sir').all()
        assert len(accounts) == 1
        assert accounts[0].class_subjects.count() == 3


def test_missing_subject_defaults_to_general(app):
    """A class teacher covers everything, which is what 'General' means."""
    with app.app_context():
        commit_teachers("Whole Class Ma'am, Class 3-A", '2026-27', 'startingpw1')
        teacher = User.query.filter_by(full_name="Whole Class Ma'am").first()
        assert teacher.class_subjects.first().subject == 'General'


def test_unreadable_rows_are_reported_and_skipped(app):
    with app.app_context():
        entries = preview_teachers("Good Ma'am, Class 5-A\nBad Ma'am, Class 99-Z\n, Class 5-A",
                                   '2026-27')
        assert entries[0]['status'] == 'create'
        assert entries[1]['status'] == 'error'
        assert 'Class 99-Z' in entries[1]['message']
        assert entries[2]['status'] == 'error'


def test_rerunning_the_same_import_does_not_duplicate(app):
    """Imports get run twice by accident; the second must be a no-op."""
    with app.app_context():
        listing = "Idempotent Ma'am, Class 6-A"
        commit_teachers(listing, '2026-27', 'startingpw1')
        created, linked, _ = commit_teachers(listing, '2026-27', 'startingpw1')

        assert created == 0
        assert linked == 0
        assert User.query.filter_by(full_name="Idempotent Ma'am").count() == 1


def test_header_row_is_ignored(app):
    with app.app_context():
        entries = preview_teachers("Teacher name, Class, Subject\nHeaderless Ma'am, Class 2-A",
                                   '2026-27')
        assert len(entries) == 1
        assert entries[0]['name'] == "Headerless Ma'am"


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
def test_student_import_creates_students(app):
    with app.app_context():
        listing = "77, Imported Child, Class 5-A, 9876543210\n78, Second Child, Class 5-A"
        entries = preview_students(listing, '2026-27')
        assert [e['status'] for e in entries] == ['create', 'create']

        created, skipped = commit_students(listing, '2026-27')
        assert (created, skipped) == (2, 0)

        child = Student.query.filter_by(roll_number='77').first()
        assert child.full_name == 'Imported Child'
        assert child.parent_contact == '9876543210'
        assert Student.query.filter_by(roll_number='78').first().parent_contact is None


def test_duplicate_roll_numbers_in_the_paste_are_caught(app):
    with app.app_context():
        entries = preview_students("55, First Child, Class 4-A\n55, Second Child, Class 4-A",
                                   '2026-27')
        assert entries[0]['status'] == 'create'
        assert entries[1]['status'] == 'error'
        assert 'twice' in entries[1]['message']


def test_a_roll_number_already_in_use_is_reported_not_overwritten(app):
    with app.app_context():
        commit_students('61, Original Child, Class 6-A', '2026-27')
        entries = preview_students('61, Different Child, Class 6-A', '2026-27')

        assert entries[0]['status'] == 'exists'
        assert 'Original Child' in entries[0]['message']

        created, skipped = commit_students('61, Different Child, Class 6-A', '2026-27')
        assert (created, skipped) == (0, 1)
        assert Student.query.filter_by(roll_number='61').first().full_name == 'Original Child'


def test_same_roll_number_is_fine_in_different_classes(app):
    with app.app_context():
        created, _ = commit_students('01, Child In Seven, Class 7-A\n'
                                     '01, Child In Eight, Class 8-A', '2026-27')
        assert created == 2


def test_tab_separated_paste_from_excel_works(app):
    with app.app_context():
        entries = preview_students('91\tExcel Child\tClass 9-A', '2026-27')
        assert entries[0]['status'] == 'create'
        assert entries[0]['name'] == 'Excel Child'


# ---------------------------------------------------------------------------
# Import screen
# ---------------------------------------------------------------------------
def test_import_page_is_admin_only(client, teacher_client):
    for c in (client, teacher_client):
        resp = c.get('/admin/import', follow_redirects=True)
        assert b'Paste your list' not in resp.data


def test_import_page_loads_for_the_principal(admin_client):
    body = admin_client.get('/admin/import').get_data(as_text=True)
    assert 'Paste your list' in body
    assert 'Teachers' in body and 'Students' in body


def test_preview_through_the_web_page_writes_nothing(admin_client, app):
    with app.app_context():
        before = User.query.count()

    resp = admin_client.post('/admin/import', data={
        'kind': 'teachers',
        'action': 'preview',
        'data': "Web Preview Ma'am, Class 5-B",
    })
    assert resp.status_code == 200
    assert b'nothing has been saved yet' in resp.data

    with app.app_context():
        assert User.query.count() == before


def test_commit_through_the_web_page_imports(admin_client, app):
    admin_client.post('/admin/import', data={
        'kind': 'students',
        'action': 'commit',
        'data': '404, Web Imported Child, Class 3-B',
    }, follow_redirects=True)

    with app.app_context():
        assert Student.query.filter_by(roll_number='404').first().full_name == 'Web Imported Child'


def test_teacher_commit_refuses_a_short_starting_password(admin_client, app):
    admin_client.post('/admin/import', data={
        'kind': 'teachers',
        'action': 'commit',
        'data': "Weak Password Ma'am, Class 2-B",
        'default_password': 'abc',
    }, follow_redirects=True)

    with app.app_context():
        assert User.query.filter_by(full_name="Weak Password Ma'am").first() is None


# ---------------------------------------------------------------------------
# Removing unused sections
# ---------------------------------------------------------------------------
def test_an_empty_section_can_be_removed(admin_client, app):
    with app.app_context():
        from app.extensions import db
        spare = Class(grade=10, section='Z', academic_year='2026-27')
        db.session.add(spare)
        db.session.commit()
        spare_id = spare.id

    admin_client.post(f'/admin/classes/{spare_id}/delete', follow_redirects=True)

    with app.app_context():
        from app.extensions import db
        assert db.session.get(Class, spare_id) is None


def test_a_section_with_students_is_never_removed(admin_client, app):
    """This guard is the reason deleting a section cannot lose records."""
    with app.app_context():
        occupied = Student.query.first().class_id

    resp = admin_client.post(f'/admin/classes/{occupied}/delete', follow_redirects=True)
    assert b'still in use' in resp.data

    with app.app_context():
        from app.extensions import db
        assert db.session.get(Class, occupied) is not None


# ---------------------------------------------------------------------------
# Import must finish inside a web request
# ---------------------------------------------------------------------------
def test_importing_a_class_of_teachers_is_not_slow(app):
    """
    Regression: importing 22 teachers hashed the same password 22 times. bcrypt
    is deliberately slow, so the request ran past the server's 30-second limit
    and the worker was killed — the user saw a 502 and nothing was saved.
    """
    import time

    listing = '\n'.join(
        f"Speed Test {n} Ma'am, Class {(n % 10) + 1}-{'A' if n % 2 else 'B'}"
        for n in range(22))

    with app.app_context():
        start = time.time()
        created, _linked, _skipped = commit_teachers(listing, '2026-27', 'startingpw1')
        elapsed = time.time() - start

    assert created == 22
    # One hash, not 22. Generous bound so this does not turn flaky on slow CI,
    # while still failing loudly if per-user hashing comes back.
    assert elapsed < 5, f'22 teachers took {elapsed:.1f}s — hashing per user again?'


def test_imported_teachers_can_actually_log_in(app):
    """The shared hash must still authenticate each teacher individually."""
    with app.app_context():
        commit_teachers("Login Check Ma'am, Class 9-B", '2026-27', 'sharedstart1')
        user = User.query.filter_by(full_name="Login Check Ma'am").first()
        assert user.check_password('sharedstart1')
        assert not user.check_password('wrongpassword')


def test_a_large_student_import_is_not_slow(app):
    """A real class list runs to hundreds of rows across the whole school."""
    import time

    listing = '\n'.join(f'{n:03d}, Speed Child {n}, Class 10-B' for n in range(1, 201))

    with app.app_context():
        start = time.time()
        created, _ = commit_students(listing, '2026-27')
        elapsed = time.time() - start

    assert created == 200
    assert elapsed < 10, f'200 students took {elapsed:.1f}s'


def test_gunicorn_timeout_is_raised_above_the_default():
    """
    The default 30s is too tight for a slow cloud instance doing real work, and
    exceeding it kills the worker mid-request with an unexplained 502.
    """
    import pathlib
    procfile = pathlib.Path('Procfile').read_text(encoding='utf-8')
    assert '--timeout' in procfile
    timeout = int(procfile.split('--timeout')[1].split()[0])
    assert timeout >= 60, f'gunicorn timeout is only {timeout}s'

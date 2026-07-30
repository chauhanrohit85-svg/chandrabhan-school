"""
Bulk import of teachers and students from a pasted or uploaded list.

Written to be forgiving about input, because the source is nearly always a
register or a spreadsheet typed by hand: headers may be missing, class names
arrive in half a dozen spellings ("Class 1-A", "1st A", "1a"), and honorifics
are part of the name. Nothing is written until the user has seen a row-by-row
preview, so a misread line is caught before it reaches the database.
"""
import csv
import io
import re
import unicodedata

from app.extensions import db
from app.models import User, Class, Student

# Written like "Nursery", "LKG", "Class 7" in the app; accepted far more loosely.
_GRADE_WORDS = {
    'nursery': -3, 'nur': -3, 'nsy': -3,
    'lkg': -2, 'l.k.g': -2, 'jrkg': -2, 'juniorkg': -2,
    'ukg': -1, 'u.k.g': -1, 'srkg': -1, 'seniorkg': -1,
}
_HONORIFICS = ("ma'am", 'maam', 'madam', 'mam', 'sir', 'mrs', 'mr', 'ms', 'miss')

MAX_ROWS = 2000


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def normalise_class(raw):
    """
    Turn a free-text class name into (grade, section), or None if unreadable.

    Accepts 'Nursery-A', 'nursery', 'LKG B', 'Class 1-A', '1st A', '1a',
    'Class 10', 'X-B'. A missing section is treated as 'A', which is by far the
    most common case in a register that only has one section per year.
    """
    if not raw:
        return None

    text = unicodedata.normalize('NFKD', str(raw)).strip().lower()
    text = text.replace('.', ' ').replace('_', ' ')
    text = re.sub(r'\b(class|std|standard|grade)\b', ' ', text)
    # 1st / 2nd / 3rd / 4th -> 1 2 3 4
    text = re.sub(r'\b(\d+)\s*(st|nd|rd|th)\b', r'\1', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text).strip()
    if not text:
        return None

    parts = text.split()

    # Trailing single letter is the section.
    section = 'A'
    if len(parts) > 1 and len(parts[-1]) == 1 and parts[-1].isalpha():
        section = parts.pop().upper()
    elif len(parts) == 1:
        # "1a" / "10b" written without a separator.
        joined = re.fullmatch(r'(\d{1,2})([a-z])', parts[0])
        if joined:
            parts = [joined.group(1)]
            section = joined.group(2).upper()

    key = ''.join(parts)
    if key in _GRADE_WORDS:
        return _GRADE_WORDS[key], section

    if key.isdigit():
        grade = int(key)
        if 1 <= grade <= 10:
            return grade, section

    return None


def clean_name(raw):
    """Tidy a person's name without stripping the honorific the school uses."""
    if not raw:
        return ''
    name = re.sub(r'\s+', ' ', str(raw).replace(' ', ' ')).strip(' ,;')
    return ' '.join(word[:1].upper() + word[1:] if word.islower() else word
                    for word in name.split())


def make_username(full_name, taken):
    """
    Build a stable, typeable username from a name.

    Honorifics are dropped here even though they are kept in the display name —
    'ruchi' is far easier to type on a phone than "ruchi.maam".
    """
    text = unicodedata.normalize('NFKD', full_name.lower())
    # Fold apostrophes away first so "ma'am" becomes the single word "maam"
    # rather than splitting into "ma" and "am", neither of which is recognised.
    text = text.replace("'", '').replace('’', '')
    text = re.sub(r"[^a-z0-9\s]", ' ', text)
    words = [w for w in text.split() if w not in _HONORIFICS]
    if not words:
        words = ['teacher']

    base = '.'.join(words[:2])[:40] or 'teacher'
    candidate, suffix = base, 2
    while candidate in taken:
        candidate = f'{base}{suffix}'
        suffix += 1
    taken.add(candidate)
    return candidate


def _read_rows(text):
    """
    Split pasted text into rows of cells.

    Handles comma, tab and semicolon separators so a paste straight out of Excel
    works as well as a typed list.
    """
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return []

    sample = text[:2000]
    delimiter = '\t' if sample.count('\t') > sample.count(',') else (
        ';' if sample.count(';') > sample.count(',') else ',')

    rows = []
    for row in csv.reader(io.StringIO(text), delimiter=delimiter):
        cells = [c.strip() for c in row]
        if any(cells):
            rows.append(cells)
    return rows


# Judged on the first cell alone. Scanning the whole row for words like "class"
# was wrong: a genuine row reads "Ruchi Ma'am, Class 1-A", so every real first
# line was being silently discarded as a header.
_HEADER_FIRST_CELLS = {
    'name', 'teacher', 'teacher name', 'full name', 'staff', 'staff name',
    'roll', 'roll no', 'roll number', 'rollno', 'sno', 's no', 'sr no',
    'serial', 'serial no', '#', 'student', 'student name',
}


def _looks_like_header(cells):
    if not cells or not cells[0]:
        return False
    first = re.sub(r'\s+', ' ', cells[0].strip().lower().replace('.', '')).strip()
    return first in _HEADER_FIRST_CELLS


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------
def preview_teachers(text, academic_year):
    """
    Work out what an import would do, without changing anything.

    Every row comes back with a status so the whole list can be shown for
    checking: 'create', 'exists' (already there, left alone) or 'error'.
    """
    rows = _read_rows(text)
    if rows and _looks_like_header(rows[0]):
        rows = rows[1:]

    taken = {u.username for u in User.query.all()}
    seen_names = {}
    results = []

    for line_no, cells in enumerate(rows[:MAX_ROWS], start=1):
        name = clean_name(cells[0] if cells else '')
        raw_class = cells[1] if len(cells) > 1 else ''
        subject = (cells[2].strip() if len(cells) > 2 else '') or 'General'

        entry = {'line': line_no, 'name': name, 'raw_class': raw_class,
                 'subject': subject, 'status': 'error', 'message': '', 'username': ''}

        if not name:
            entry['message'] = 'No teacher name in this row.'
            results.append(entry)
            continue

        parsed = normalise_class(raw_class)
        if not parsed:
            entry['message'] = f'Could not understand the class "{raw_class}".'
            results.append(entry)
            continue

        grade, section = parsed
        cls = Class.query.filter_by(grade=grade, section=section,
                                    academic_year=academic_year).first()
        entry['class_name'] = f'{Class.GRADE_MAP.get(grade, grade)}-{section}'
        if not cls:
            entry['message'] = f'{entry["class_name"]} does not exist yet.'
            results.append(entry)
            continue

        entry['class_id'] = cls.id

        # One account per person, even when they appear on several rows.
        if name in seen_names:
            entry['username'] = seen_names[name]
            entry['status'] = 'create'
            entry['message'] = 'Same teacher, additional class.'
            results.append(entry)
            continue

        existing = User.query.filter_by(full_name=name, role='teacher').first()
        if existing:
            entry['username'] = existing.username
            entry['status'] = 'exists'
            entry['message'] = 'Already has an account; class will be linked.'
        else:
            entry['username'] = make_username(name, taken)
            entry['status'] = 'create'
            entry['message'] = 'New account.'

        seen_names[name] = entry['username']
        results.append(entry)

    return results


def commit_teachers(text, academic_year, default_password):
    """Apply a previewed teacher import. Returns (created, linked, skipped)."""
    entries = preview_teachers(text, academic_year)
    created = linked = skipped = 0

    from app.models import TeacherClassSubject

    for entry in entries:
        if entry['status'] == 'error':
            skipped += 1
            continue

        user = User.query.filter_by(username=entry['username']).first()
        if not user:
            user = User(username=entry['username'], full_name=entry['name'],
                        role='teacher', assigned_class_id=entry['class_id'])
            user.set_password(default_password)
            db.session.add(user)
            db.session.flush()
            created += 1
        elif user.assigned_class_id is None:
            user.assigned_class_id = entry['class_id']

        mapping = TeacherClassSubject.query.filter_by(
            teacher_id=user.id, class_id=entry['class_id'], subject=entry['subject']).first()
        if not mapping:
            db.session.add(TeacherClassSubject(
                teacher_id=user.id, class_id=entry['class_id'], subject=entry['subject']))
            linked += 1

    db.session.commit()
    return created, linked, skipped


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
def preview_students(text, academic_year):
    """Same contract as preview_teachers, for the student roster."""
    rows = _read_rows(text)
    if rows and _looks_like_header(rows[0]):
        rows = rows[1:]

    results = []
    seen = set()

    for line_no, cells in enumerate(rows[:MAX_ROWS], start=1):
        roll = (cells[0].strip() if cells else '')
        name = clean_name(cells[1] if len(cells) > 1 else '')
        raw_class = cells[2] if len(cells) > 2 else ''
        contact = (cells[3].strip() if len(cells) > 3 else '')

        entry = {'line': line_no, 'roll': roll, 'name': name, 'raw_class': raw_class,
                 'contact': contact, 'status': 'error', 'message': ''}

        if not name or not roll:
            entry['message'] = 'Both a roll number and a name are needed.'
            results.append(entry)
            continue

        parsed = normalise_class(raw_class)
        if not parsed:
            entry['message'] = f'Could not understand the class "{raw_class}".'
            results.append(entry)
            continue

        grade, section = parsed
        cls = Class.query.filter_by(grade=grade, section=section,
                                    academic_year=academic_year).first()
        entry['class_name'] = f'{Class.GRADE_MAP.get(grade, grade)}-{section}'
        if not cls:
            entry['message'] = f'{entry["class_name"]} does not exist yet.'
            results.append(entry)
            continue

        entry['class_id'] = cls.id

        key = (cls.id, roll)
        if key in seen:
            entry['message'] = f'Roll {roll} appears twice for {entry["class_name"]}.'
            results.append(entry)
            continue
        seen.add(key)

        existing = Student.query.filter_by(class_id=cls.id, roll_number=roll).first()
        if existing:
            entry['status'] = 'exists'
            entry['message'] = f'Roll {roll} already used by {existing.full_name}.'
        else:
            entry['status'] = 'create'
            entry['message'] = 'New student.'

        results.append(entry)

    return results


def commit_students(text, academic_year):
    """Apply a previewed student import. Returns (created, skipped)."""
    entries = preview_students(text, academic_year)
    created = skipped = 0

    for entry in entries:
        if entry['status'] != 'create':
            skipped += 1
            continue
        db.session.add(Student(
            roll_number=entry['roll'],
            full_name=entry['name'],
            class_id=entry['class_id'],
            parent_contact=entry['contact'] or None,
        ))
        created += 1

    db.session.commit()
    return created, skipped

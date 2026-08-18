"""
Tests for password self-service and the boundary between Principal and Director.

Accounts are handed to real staff, so two things must hold: everyone can rotate
their own password, and the Principal cannot reach the Director's account.
"""
import pytest

from app.models import User


def _login(client, username, password):
    return client.post('/auth/login',
                       data={'username': username, 'password': password},
                       follow_redirects=True)


# ---------------------------------------------------------------------------
# Self-service password change
# ---------------------------------------------------------------------------
def test_change_password_page_reachable_by_every_role(app):
    """Director, principal and teacher all get a way to change their own password."""
    for username, password in [('director', 'director123'),
                               ('test_admin', 'admin123'),
                               ('test_teacher1', 'teacher123')]:
        client = app.test_client()
        _login(client, username, password)
        resp = client.get('/auth/password')
        assert resp.status_code == 200, f'{username} cannot reach the password page'
        assert b'Change my password' in resp.data


def test_change_password_requires_login(client):
    resp = client.get('/auth/password')
    assert resp.status_code in (301, 302)
    assert '/auth/login' in resp.headers['Location']


def test_password_actually_changes_and_old_one_stops_working(app):
    """The whole point: the credential a user was given can be retired."""
    with app.app_context():
        from app.extensions import db
        rotating = User(username='rotate_me', full_name='Rotating User', role='teacher')
        rotating.set_password('startingpw1')
        db.session.add(rotating)
        db.session.commit()

    client = app.test_client()
    _login(client, 'rotate_me', 'startingpw1')

    resp = client.post('/auth/password', data={
        'current_password': 'startingpw1',
        'new_password': 'a-much-better-one',
        'confirm_password': 'a-much-better-one',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        user = User.query.filter_by(username='rotate_me').first()
        assert user.check_password('a-much-better-one')
        assert not user.check_password('startingpw1')


def test_wrong_current_password_is_rejected(app):
    with app.app_context():
        from app.extensions import db
        user = User(username='guard_me', full_name='Guarded', role='teacher')
        user.set_password('originalpw1')
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    _login(client, 'guard_me', 'originalpw1')

    client.post('/auth/password', data={
        'current_password': 'not-the-right-one',
        'new_password': 'attackers-choice',
        'confirm_password': 'attackers-choice',
    }, follow_redirects=True)

    with app.app_context():
        assert User.query.filter_by(username='guard_me').first().check_password('originalpw1')


@pytest.mark.parametrize('new, confirm, reason', [
    ('short', 'short', 'too short'),
    ('long-enough-one', 'different-entirely', 'mismatched confirmation'),
])
def test_weak_or_mismatched_passwords_are_refused(app, new, confirm, reason):
    with app.app_context():
        from app.extensions import db
        username = f'reject_{len(new)}_{len(confirm)}'
        user = User(username=username, full_name='Reject Case', role='teacher')
        user.set_password('originalpw1')
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    _login(client, username, 'originalpw1')
    client.post('/auth/password', data={
        'current_password': 'originalpw1',
        'new_password': new,
        'confirm_password': confirm,
    }, follow_redirects=True)

    with app.app_context():
        assert User.query.filter_by(username=username).first().check_password('originalpw1'), \
            f'password was changed despite {reason}'


# ---------------------------------------------------------------------------
# Principal cannot escalate to Director
# ---------------------------------------------------------------------------
def test_principal_cannot_open_the_director_account(admin_client, app):
    with app.app_context():
        director_id = User.query.filter_by(role='director').first().id

    resp = admin_client.get(f'/admin/users/{director_id}/edit', follow_redirects=True)
    assert resp.status_code == 200
    assert b'only be managed by the Director' in resp.data


def test_principal_cannot_reset_the_director_password(admin_client, app):
    """
    edit_user accepts any user id, so without a guard the Principal could reset
    the Director's password by URL and then sign in as the super-admin.
    """
    with app.app_context():
        director = User.query.filter_by(role='director').first()
        director_id = director.id

    admin_client.post(f'/admin/users/{director_id}/edit', data={
        'full_name': 'Hijacked',
        'role': 'admin',
        'new_password': 'principal-picked-this',
        'is_active': 'on',
    }, follow_redirects=True)

    with app.app_context():
        director = User.query.get(director_id)
        assert not director.check_password('principal-picked-this')
        assert director.role == 'director'
        assert director.full_name != 'Hijacked'


def test_principal_cannot_deactivate_the_director(admin_client, app):
    with app.app_context():
        director_id = User.query.filter_by(role='director').first().id

    admin_client.post(f'/admin/users/{director_id}/toggle', follow_redirects=True)

    with app.app_context():
        assert User.query.get(director_id).is_active == 1


def test_principal_cannot_create_an_admin_account(admin_client, app):
    admin_client.post('/admin/users/add', data={
        'username': 'sneaky_admin',
        'full_name': 'Sneaky Admin',
        'password': 'longenoughpw',
        'role': 'admin',
    }, follow_redirects=True)

    with app.app_context():
        assert User.query.filter_by(username='sneaky_admin').first() is None


def test_principal_can_still_manage_teachers(admin_client, app):
    """The lockdown must not get in the way of the Principal's actual job."""
    with app.app_context():
        teacher_id = User.query.filter_by(role='teacher').first().id

    resp = admin_client.get(f'/admin/users/{teacher_id}/edit')
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Director staff management
# ---------------------------------------------------------------------------
def test_director_sees_every_account(director_client, app):
    with app.app_context():
        expected = User.query.count()

    resp = director_client.get('/director/staff')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f'{expected} total' in body
    # The Principal's account must be visible — this is the recovery path.
    assert 'test_admin' in body


def test_director_can_reset_an_administrator_password(director_client, app):
    """
    The Director is the recovery path for an account the Principal cannot touch.

    Uses a throwaway administrator rather than the shared `test_admin` fixture
    user: rotating that one would break every later test that signs in as the
    Principal.
    """
    with app.app_context():
        from app.extensions import db
        target = User(username='second_principal', full_name='Second Principal', role='admin')
        target.set_password('originalpw1')
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    director_client.post(f'/director/staff/{target_id}/password',
                         data={'new_password': 'director-issued-pw'},
                         follow_redirects=True)

    with app.app_context():
        assert User.query.get(target_id).check_password('director-issued-pw')


def test_director_reset_rejects_a_short_password(director_client, app):
    with app.app_context():
        user = User.query.filter_by(username='test_teacher1').first()
        user_id, before = user.id, user.password_hash

    director_client.post(f'/director/staff/{user_id}/password',
                         data={'new_password': 'abc'}, follow_redirects=True)

    with app.app_context():
        assert User.query.get(user_id).password_hash == before


def test_director_cannot_deactivate_themselves(director_client, app):
    """Disabling your own super-admin account would lock everyone out of it."""
    with app.app_context():
        director_id = User.query.filter_by(role='director').first().id

    director_client.post(f'/director/staff/{director_id}/toggle', follow_redirects=True)

    with app.app_context():
        assert User.query.get(director_id).is_active == 1


def test_staff_page_is_director_only(admin_client, teacher_client):
    """Assert on the outcome rather than the wording of the flash message."""
    for client in (admin_client, teacher_client):
        redirected = client.get('/director/staff')
        assert redirected.status_code in (301, 302)
        assert '/auth/login' in redirected.headers['Location']

        body = client.get('/director/staff', follow_redirects=True).get_data(as_text=True)
        assert 'All accounts' not in body, 'staff list leaked to a non-director'


def test_password_reset_endpoints_are_director_only(admin_client, app):
    """The guard must cover the POST actions, not just the page that links to them."""
    with app.app_context():
        target = User.query.filter_by(username='test_teacher1').first()
        target_id, before = target.id, target.password_hash

    admin_client.post(f'/director/staff/{target_id}/password',
                      data={'new_password': 'principal-tried-this'},
                      follow_redirects=True)

    with app.app_context():
        assert User.query.get(target_id).password_hash == before


def test_admin_password_field_cannot_silently_fail(admin_client, app):
    """
    The reset field must tell the browser its minimum length. Without it the
    form submits, the server rejects it, and the warning renders at the top of
    the page — off screen on a phone, so it looks like nothing happened.
    """
    with app.app_context():
        teacher_id = User.query.filter_by(role='teacher').first().id

    body = admin_client.get(f'/admin/users/{teacher_id}/edit').get_data(as_text=True)
    assert 'name="new_password"' in body
    assert 'minlength="8"' in body
    assert 'At least 8 characters' in body


def test_principal_can_reset_a_teacher_password(admin_client, app):
    """The end-to-end path a principal actually uses when a teacher forgets."""
    with app.app_context():
        from app.extensions import db
        teacher = User(username='forgetful', full_name='Forgetful Ma\'am', role='teacher')
        teacher.set_password('originalpw1')
        db.session.add(teacher)
        db.session.commit()
        teacher_id = teacher.id

    admin_client.post(f'/admin/users/{teacher_id}/edit', data={
        'full_name': "Forgetful Ma'am",
        'role': 'teacher',
        'new_password': 'freshstart2026',
        'is_active': 'on',
    }, follow_redirects=True)

    with app.app_context():
        teacher = User.query.get(teacher_id)
        assert teacher.check_password('freshstart2026')
        assert not teacher.check_password('originalpw1')

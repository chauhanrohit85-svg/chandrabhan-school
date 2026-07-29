"""
Tests for recovering a lost master password via an environment variable.

The school has no technical administrator, so "read the deploy log" is not a
usable recovery path. Setting BOOTSTRAP_*_PASSWORD must reliably let someone
back in — and must not quietly undo a password they later change in the app.
"""
from app import create_app, _apply_bootstrap_password_overrides
from app.models import User, AppSetting


def _fresh_app(monkeypatch, tmp_path, name, **env):
    for var in ('SECRET_KEY', 'FLASK_ENV', 'RENDER', 'RENDER_SERVICE_ID',
                'DATABASE_URL', 'BOOTSTRAP_DIRECTOR_PASSWORD',
                'BOOTSTRAP_ADMIN_PASSWORD', 'BOOTSTRAP_TEACHER_PASSWORD'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('SQLITE_DB_PATH', str(tmp_path / f'{name}.db'))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app('development')


def test_director_password_can_be_recovered_from_the_environment(monkeypatch, tmp_path):
    app = _fresh_app(monkeypatch, tmp_path, 'recover',
                     BOOTSTRAP_DIRECTOR_PASSWORD='RecoveredByOwner1')

    with app.app_context():
        director = User.query.filter_by(username='director').first()
        assert director is not None
        assert director.check_password('RecoveredByOwner1')


def test_principal_and_teachers_can_be_recovered_too(monkeypatch, tmp_path):
    app = _fresh_app(monkeypatch, tmp_path, 'recover_all',
                     BOOTSTRAP_ADMIN_PASSWORD='PrincipalPw12345',
                     BOOTSTRAP_TEACHER_PASSWORD='TeacherPw123456')

    with app.app_context():
        assert User.query.filter_by(username='principal').first().check_password('PrincipalPw12345')
        for n in range(1, 6):
            assert User.query.filter_by(username=f'teacher{n}').first().check_password('TeacherPw123456')


def test_a_password_changed_in_the_app_is_not_undone_by_a_redeploy(monkeypatch, tmp_path):
    """
    The variable is applied once. Leaving it set must not revert a password the
    user later changed in the app, which would be baffling and would keep
    resetting their account on every deploy.
    """
    app = _fresh_app(monkeypatch, tmp_path, 'no_revert',
                     BOOTSTRAP_DIRECTOR_PASSWORD='FirstRecovery123')

    with app.app_context():
        from app.extensions import db
        director = User.query.filter_by(username='director').first()
        assert director.check_password('FirstRecovery123')

        # The user signs in and picks their own password.
        director.set_password('ChosenInTheApp99')
        db.session.commit()

    # A redeploy with the same variable still in place.
    _apply_bootstrap_password_overrides(app)

    with app.app_context():
        director = User.query.filter_by(username='director').first()
        assert director.check_password('ChosenInTheApp99'), \
            'the environment variable overwrote a password chosen in the app'
        assert not director.check_password('FirstRecovery123')


def test_changing_the_variable_applies_again(monkeypatch, tmp_path):
    """A second lockout must be recoverable by setting a different value."""
    app = _fresh_app(monkeypatch, tmp_path, 'second_time',
                     BOOTSTRAP_DIRECTOR_PASSWORD='FirstRecovery123')

    with app.app_context():
        from app.extensions import db
        director = User.query.filter_by(username='director').first()
        director.set_password('SomethingElse123')
        db.session.commit()

    monkeypatch.setenv('BOOTSTRAP_DIRECTOR_PASSWORD', 'SecondRecovery456')
    _apply_bootstrap_password_overrides(app)

    with app.app_context():
        assert User.query.filter_by(username='director').first().check_password('SecondRecovery456')


def test_nothing_happens_when_no_variable_is_set(monkeypatch, tmp_path):
    app = _fresh_app(monkeypatch, tmp_path, 'noop')
    assert _apply_bootstrap_password_overrides(app) == []


def test_applying_records_a_marker_rather_than_the_password(monkeypatch, tmp_path):
    """The stored fingerprint must not be the password itself."""
    secret = 'NeverStoreMePlain1'
    app = _fresh_app(monkeypatch, tmp_path, 'marker', BOOTSTRAP_DIRECTOR_PASSWORD=secret)

    with app.app_context():
        from app.extensions import db
        marker = db.session.get(AppSetting, 'bootstrap_pw:director')
        assert marker is not None
        assert secret not in marker.value
        assert len(marker.value) == 64      # sha256 hex digest

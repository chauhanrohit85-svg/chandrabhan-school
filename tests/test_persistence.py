"""
Tests for Data Persistence and Non-Destructive Startup Seeding.
"""
import pytest
from app import create_app
from app.models import User, Class
from migrations.init_db import seed


def test_startup_seeding_preserves_existing_user(app):
    """
    Verify that calling seed(app) when database already has users does NOT drop tables or overwrite existing accounts.
    """
    with app.app_context():
        # Count existing users
        initial_user_count = User.query.count()
        assert initial_user_count > 0

        # Add a new custom user to simulate a runtime account
        custom_user = User(username='persistent_teacher', full_name='Persistent Teacher', role='teacher')
        custom_user.set_password('secure123')
        from app.extensions import db
        db.session.add(custom_user)
        db.session.commit()

        # Run non-destructive startup seed
        seed(app)

        # Ensure custom_user still exists and was not erased
        rechecked_user = User.query.filter_by(username='persistent_teacher').first()
        assert rechecked_user is not None
        assert rechecked_user.full_name == 'Persistent Teacher'

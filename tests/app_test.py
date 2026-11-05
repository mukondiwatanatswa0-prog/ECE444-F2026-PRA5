import os
import pytest
import json
from pathlib import Path
from project.app import app, db

from project import models

TEST_DB = "test.db"


@pytest.fixture
def client():
    BASE_DIR = Path(__file__).resolve().parent.parent
    app.config["TESTING"] = True
    app.config["DATABASE"] = BASE_DIR.joinpath(TEST_DB)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR.joinpath(TEST_DB)}"

    with app.app_context():
        db.create_all()  # setup
        yield app.test_client()  # tests run here
        db.drop_all()  # teardown


def login(client, username, password):
    """Login helper function"""
    return client.post(
        "/login",
        data=dict(username=username, password=password),
        follow_redirects=True,
    )


def logout(client):
    """Logout helper function"""
    return client.get("/logout", follow_redirects=True)


def test_index(client):
    response = client.get("/", content_type="html/text")
    assert response.status_code == 200


def test_database(client):
    """initial test. ensure that the database exists"""
    tester = Path("test.db").is_file()
    assert tester


def test_empty_db(client):
    """Ensure database is blank"""
    rv = client.get("/")
    assert b"No entries yet. Add some!" in rv.data


def test_login_logout(client):
    """Test login and logout using helper functions"""
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"])
    assert b"You were logged in" in rv.data
    rv = logout(client)
    assert b"You were logged out" in rv.data
    rv = login(client, app.config["USERNAME"] + "x", app.config["PASSWORD"])
    assert b"Invalid username" in rv.data
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"] + "x")
    assert b"Invalid password" in rv.data


def test_messages(client):
    """Ensure that user can post messages"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.post(
        "/add",
        data=dict(title="<Hello>", text="<strong>HTML</strong> allowed here"),
        follow_redirects=True,
    )
    assert b"No entries here so far" not in rv.data
    assert b"&lt;Hello&gt;" in rv.data
    assert b"<strong>HTML</strong> allowed here" in rv.data


def test_delete_message(client):
    """Ensure the messages are being deleted"""
    rv = client.get("/delete/1")
    data = json.loads(rv.data)
    assert data["status"] == 0
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.get("/delete/1")
    data = json.loads(rv.data)
    assert data["status"] == 1


def test_delete_requires_login(client):
    """Test that unauthenticated users cannot delete posts."""

    # Create a post in the database
    with app.app_context():
        post = models.Post("Test Title", "Test Content")
        db.session.add(post)
        db.session.commit()
        post_id = post.id

    # Attempt to delete the post without logging in
    response = client.get(f"/delete/{post_id}")

    # Verify that access is denied
    assert response.status_code == 401
    assert response.get_json()["status"] == 0

    # Verify that the post still exists in the database
    with app.app_context():
        post = db.session.get(models.Post, post_id)
        assert post is not None


def test_search_multiple_matches(client):
    """Test that search returns multiple matching posts."""

    with app.app_context():
        db.session.add(models.Post("Python Basics", "Learning Python"))
        db.session.add(models.Post("Python Flask", "Web development"))
        db.session.add(models.Post("Java Tutorial", "Learning Java"))
        db.session.commit()

    response = client.get("/search/?query=Python")

    assert response.status_code == 200
    assert b"Python Basics" in response.data
    assert b"Python Flask" in response.data
    assert b"Java Tutorial" not in response.data


def test_search_no_matches(client):
    """Test that search returns no posts when nothing matches."""

    with app.app_context():
        db.session.add(models.Post("Python Basics", "Learning Python"))
        db.session.add(models.Post("Flask Tutorial", "Web development"))
        db.session.commit()

    response = client.get("/search/?query=Chemistry")

    assert response.status_code == 200
    assert b"Python Basics" not in response.data
    assert b"Flask Tutorial" not in response.data
    assert b'class="entry"' not in response.data


def test_search_correct_matches(client):
    """Test that search matches both post titles and content."""

    with app.app_context():
        db.session.add(models.Post("Flask Guide", "Introduction to web development"))
        db.session.add(models.Post("Programming", "Learning Flask applications"))
        db.session.add(models.Post("Python Basics", "Introduction to Python"))
        db.session.commit()

    response = client.get("/search/?query=Flask")

    assert response.status_code == 200
    assert b"Flask Guide" in response.data
    assert b"Programming" in response.data
    assert b"Python Basics" not in response.data


def test_search_case_insensitive(client):
    """Test that searching is case insensitive."""

    with app.app_context():
        db.session.add(models.Post("Python Basics", "Learning programming"))
        db.session.add(models.Post("PYTHON Advanced", "Advanced topics"))
        db.session.add(models.Post("Java Tutorial", "Learning Java"))
        db.session.commit()

    response_lower = client.get("/search/?query=python")
    response_upper = client.get("/search/?query=PYTHON")
    response_mixed = client.get("/search/?query=PyThOn")

    for response in [response_lower, response_upper, response_mixed]:
        assert response.status_code == 200
        assert b"Python Basics" in response.data
        assert b"PYTHON Advanced" in response.data
        assert b"Java Tutorial" not in response.data

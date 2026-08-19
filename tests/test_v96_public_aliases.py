from fastapi.testclient import TestClient
from app.main import app


def test_lowercase_home_and_courses_aliases():
    client = TestClient(app)
    home = client.get('/home', follow_redirects=False)
    assert home.status_code == 200
    courses = client.get('/courses', follow_redirects=False)
    assert courses.status_code == 303
    assert courses.headers['location'] == '/#courses'

from app.crud.user import crud_user
from app.schemas.user import UserCreate


def test_login_success(client, db):
    crud_user.create(db, UserCreate(username="testuser", password="testpass"))
    res = client.post("/api/v1/auth/token", data={"username": "testuser", "password": "testpass"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client, db):
    crud_user.create(db, UserCreate(username="testuser", password="testpass"))
    res = client.post("/api/v1/auth/token", data={"username": "testuser", "password": "wrong"})
    assert res.status_code == 401

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from app.auth import hash_token
from app.main import app, init_database
from app.models import User
from app.util import next_seq, now_iso


@pytest.fixture()
def database(tmp_path):
    dbmod.init_engine(tmp_path / "test.db")
    init_database()
    yield
    dbmod.get_engine().dispose()


@pytest.fixture()
def db(database):
    session = dbmod.new_session()
    yield session
    session.close()


def _make_user(db, name: str, gender: str = "male") -> tuple[User, str]:
    token = f"token-{name}"
    user = User(name=name, gender=gender, height_cm=175, age=30, target_weight_kg=70,
                token_hash=hash_token(token), updated_at=now_iso(), server_seq=next_seq(db))
    db.add(user)
    db.commit()
    return user, token


@pytest.fixture()
def user(db):
    return _make_user(db, "teszt")


@pytest.fixture()
def other_user(db):
    return _make_user(db, "masik", "female")


@pytest.fixture()
def client(database):
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

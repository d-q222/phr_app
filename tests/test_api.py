import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from tests.test_basic import _two_profiles_with_allergies


@pytest.fixture
def client(tmp_path):
    db_path, alice, bob, _bob_record = _two_profiles_with_allergies(tmp_path)

    test_engine = create_engine(
    f"sqlite:///{db_path}",
    connect_args={"check_same_thread": False}
    )

    SessionLocal = sessionmaker(bind=test_engine)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    yield client, alice, bob 

    app.dependency_overrides.clear()


def test_listing_people(client):
    client, alice, bob = client
    response = client.get("/people")
    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["Alice", "Bob"]
    assert [p["id"] for p in response.json()] == [alice, bob]

def test_getting_people(client):
    client, alice, bob = client
    response = client.get(f"/people/{alice}")
    assert response.status_code == 200
    assert response.json()["name"] == "Alice"

def test_missing_id(client):
    client, alice, bob = client
    response = client.get("/people/999")
    assert response.status_code == 404

def test_creating_person(client):
    client, alice, bob = client
    new_person_data = {
        "name": "Charlie",
        "date_of_birth": "1990-01-01",
        "sex": "Female",
        "relationship": "Child",
        "emergency_contact": "Alice",
        "notes": "New family member"
    }
    response = client.post("/people", json = new_person_data)
    data = response.json()
    assert response.status_code == 201
    assert data['id'] != alice and data['id'] != bob
    assert data['name'] == "Charlie"
    assert data['date_of_birth'] == "1990-01-01"
    assert data['sex'] == "Female"
    assert data['relationship'] == "Child"
    assert data['emergency_contact'] == "Alice"
    assert data['notes'] == "New family member"
    assert client.get("/people/count").json()['people_count'] == 3

def test_create_with_name_only(client):
    client, alice, bob = client
    new_person_data = {'name': 'X'}
    response = client.post("/people", json = new_person_data)
    assert response.status_code == 201

def test_create_with_empty_data(client):
    client, alice, bob = client
    new_person_data = {}
    response = client.post("/people", json = new_person_data)
    assert response.status_code == 422
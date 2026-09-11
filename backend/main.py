from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import People
from backend.schemas import PersonCreate, PersonOut

app = FastAPI()
DbSession = Annotated[Session, Depends(get_db)]

@app.get("/health")
def read_root():
    return {"status": "ok"}

@app.get("/people/count")
def get_people_count(db: DbSession):
    people_count = db.query(People).count()
    return {'people_count': people_count}

@app.get("/people", response_model = list[PersonOut])
def list_people(db: DbSession):
    people = db.query(People).order_by(People.id).all()
    return people

@app.get("/people/{person_id}", response_model = PersonOut)
def get_person(person_id: int, db: DbSession):
    person = db.query(People).filter(People.id == person_id).first()
    if person is None:
            raise HTTPException(status_code = 404, detail = "Person not found")
    return person

@app.post("/people", response_model = PersonOut, status_code = 201)
def create_person(body: PersonCreate, db: DbSession):
    new_person = People(**body.model_dump())
    db.add(new_person)
    db.commit()
    db.refresh(new_person)
    return new_person

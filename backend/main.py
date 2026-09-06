from fastapi import FastAPI, Depends
from backend.database import get_db
from backend.models import People
from sqlalchemy.orm import Session
from backend.schemas import PersonOut

app = FastAPI()

@app.get("/health")
def read_root():
    return {"status": "ok"}

@app.get("/people/count")
def get_people_count(db: Session = Depends(get_db)):
    people_count = db.query(People).count()
    return {'people_count': people_count}

@app.get("/people", response_model = list[PersonOut])
def list_people(db: Session = Depends(get_db)):
    people = db.query(People).order_by(People.id).all()
    return people
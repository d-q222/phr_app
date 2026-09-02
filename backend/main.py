from fastapi import FastAPI
from database import SessionLocal
from models import People

app = FastAPI()

@app.get("/health")
def read_root():
    return {"status": "ok"}

@app.get("/people/count")
def get_people_count():
    with SessionLocal() as db:
        people_count = db.query(People).count()
    return {'people_count': people_count}
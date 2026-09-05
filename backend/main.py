from fastapi import FastAPI, Depends
from database import get_db
from models import People
from sqlalchemy.orm import Session

app = FastAPI()

@app.get("/health")
def read_root():
    return {"status": "ok"}

@app.get("/people/count")
def get_people_count(db: Session = Depends(get_db)):
    people_count = db.query(People).count()
    return {'people_count': people_count}
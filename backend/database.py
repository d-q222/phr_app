from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

engine = create_engine(
    "sqlite:///./data/phr.db",
    connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind = engine)

def get_db():
    with SessionLocal() as db:
        yield db


class Base(DeclarativeBase):
    pass









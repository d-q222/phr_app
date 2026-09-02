from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

engine = create_engine(
    "sqlite:///./data/phr.db",
    connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind = engine)

class Base(DeclarativeBase):
    pass









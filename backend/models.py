from backend.database import Base
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

class People(Base):
    __tablename__ = 'people'
    id: Mapped[int]= mapped_column(primary_key = True)
    name: Mapped[str]
    date_of_birth: Mapped[str | None] #change to date?
    sex: Mapped[str | None]
    relationship: Mapped[str | None]
    emergency_contact: Mapped[str | None]
    notes: Mapped[str | None]
    profile_password_enabled: Mapped[int | None] #change to boolean?
    profile_password_hash: Mapped[str | None]
    profile_password_hint: Mapped[str | None]
    created_at: Mapped[str]  #Mapped[datetime] = mapped_column(default = datetime.now) ???
    updated_at: Mapped[str]  #Mapped[datetime] = mapped_column(default = datetime.now) ???


class Allergies(Base):
    __tablename__ = 'allergies'
    id: Mapped[int] = mapped_column(primary_key = True)
    person_id: Mapped[int] = mapped_column(ForeignKey('people.id')) #add foreign key to people table??
    allergen: Mapped[str]
    reaction: Mapped[str | None]
    severity: Mapped[str | None]
    notes: Mapped[str | None]
    created_at: Mapped[str] #Mapped[datetime] = mapped_column(default = datetime.now) ???
    updated_at: Mapped[str] #Mapped[datetime] = mapped_column(default = datetime.now) ???




from pydantic import BaseModel, ConfigDict

class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    id: int
    name: str
    date_of_birth: str | None = None
    sex: str | None = None
    relationship: str | None = None
    emergency_contact: str | None = None
    notes: str | None = None

class PersonCreate(BaseModel):
    model_config = ConfigDict()
    name: str
    date_of_birth: str | None = None
    sex: str | None = None 
    relationship: str | None = None
    emergency_contact: str | None = None
    notes: str | None = None
    
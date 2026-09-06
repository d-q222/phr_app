from pydantic import BaseModel, ConfigDict

class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes = True)
    id: int
    name: str
    date_of_birth: str | None

"""Domain Entities - Auth"""
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from typing import Optional

class User(BaseModel):
    """User Entity"""
    user_id: UUID = Field(default_factory=uuid4)
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: bool = False
    
    class Config:
        from_attributes = True

class UserInDB(User):
    """User with hashed password for DB storage"""
    hashed_password: str

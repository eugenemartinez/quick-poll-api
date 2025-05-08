from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class PollOption(BaseModel):
    id: Optional[int]
    text: str
    votes: Optional[int] = 0

    class Config:
        orm_mode = True

class Poll(BaseModel):
    id: Optional[UUID]
    question: str
    creator_display_name: Optional[str]
    allow_multiple_selections: bool = False
    voting_security_level: str = "cookie_basic"
    is_public: bool = False
    modification_code: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    options: List[PollOption] = []

    class Config:
        orm_mode = True
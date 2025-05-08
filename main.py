from database import engine, get_db
import models
from schemas import Poll as PollSchema, PollOption as PollOptionSchema  # Import Pydantic models
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

# Initialize database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to Quick Poll!"}

@app.post("/api/polls/", response_model=PollSchema)
def create_poll(poll: PollSchema, db: Session = Depends(get_db)):
    db_poll = models.Poll(
        question=poll.question,
        creator_display_name=poll.creator_display_name,
        allow_multiple_selections=poll.allow_multiple_selections,
        voting_security_level=poll.voting_security_level,
        is_public=poll.is_public,
        modification_code=poll.modification_code,
    )
    db.add(db_poll)
    db.commit()
    db.refresh(db_poll)
    return db_poll

@app.get("/api/polls/", response_model=List[PollSchema])
def list_polls(db: Session = Depends(get_db)):
    return db.query(models.Poll).all()

@app.get("/api/poll/{poll_id}", response_model=PollSchema)
def get_poll(poll_id: str, db: Session = Depends(get_db)):
    poll = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    return poll
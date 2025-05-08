from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from database import Base  # Use absolute import

class Poll(Base):
    __tablename__ = "poll"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question = Column(String, nullable=False)
    creator_display_name = Column(String, nullable=True)
    allow_multiple_selections = Column(Boolean, default=False)
    voting_security_level = Column(String, default="cookie_basic")
    is_public = Column(Boolean, default=False)
    modification_code = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    options = relationship("PollOption", back_populates="poll", cascade="all, delete-orphan")


class PollOption(Base):
    __tablename__ = "poll_option"

    id = Column(Integer, primary_key=True, index=True)
    poll_id = Column(UUID(as_uuid=True), ForeignKey("poll.id"), nullable=False)
    text = Column(String, nullable=False)
    votes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    poll = relationship("Poll", back_populates="options")
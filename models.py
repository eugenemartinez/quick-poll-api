from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, DateTime, UniqueConstraint, Text # Added Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func # For server_default=func.now()
# from datetime import datetime # Not strictly needed if using server_default for all timestamps
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
    modification_code = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    options = relationship("PollOption", back_populates="poll", cascade="all, delete-orphan")
    individual_votes = relationship("IndividualVote", back_populates="poll", cascade="all, delete-orphan")
    edit_history = relationship("PollEditHistory", back_populates="poll", cascade="all, delete-orphan") # Added relationship


class PollOption(Base):
    __tablename__ = "poll_option"

    id = Column(Integer, primary_key=True, index=True)
    poll_id = Column(UUID(as_uuid=True), ForeignKey("poll.id"), nullable=False)
    text = Column(String, nullable=False)
    votes = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    poll = relationship("Poll", back_populates="options")
    # Renamed for consistency with IndividualVote.option relationship
    individual_votes_on_option = relationship("IndividualVote", back_populates="option", cascade="all, delete-orphan")


class IndividualVote(Base):
    __tablename__ = "individual_vote"

    id = Column(Integer, primary_key=True, index=True)
    poll_id = Column(UUID(as_uuid=True), ForeignKey("poll.id"), nullable=False)
    option_id = Column(Integer, ForeignKey("poll_option.id"), nullable=False)
    voter_token = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now()) # Renamed from voted_at for consistency

    poll = relationship("Poll", back_populates="individual_votes")
    # This back_populates PollOption.individual_votes_on_option
    option = relationship("PollOption", back_populates="individual_votes_on_option")

    __table_args__ = (UniqueConstraint('poll_id', 'option_id', 'voter_token', name='uq_poll_option_voter_token'),)


# New Model for Poll Edit History
class PollEditHistory(Base):
    __tablename__ = "poll_edit_history"

    id = Column(Integer, primary_key=True, index=True)
    poll_id = Column(UUID(as_uuid=True), ForeignKey("poll.id"), nullable=False, index=True)
    edited_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    field_changed = Column(String, nullable=False) # e.g., "question", "option_text", "option_added", "is_public"
    
    # If the change relates to a specific option
    option_id_changed = Column(Integer, ForeignKey("poll_option.id", ondelete="SET NULL"), nullable=True)
    
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    
    change_description = Column(Text, nullable=True)

    poll = relationship("Poll", back_populates="edit_history")
    # Optional: Relationship to the specific option that was changed, if option_id_changed is set.
    # This helps in querying/displaying option details directly from history if needed.
    # Ensure PollOption does not have a back_populates for this unless you define a specific collection on PollOption for its history entries.
    changed_option_details = relationship("PollOption", foreign_keys=[option_id_changed])
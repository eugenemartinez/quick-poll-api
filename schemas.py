from pydantic import BaseModel, Field, validator, model_validator
from typing import List, Optional, Set
from uuid import UUID
from datetime import datetime
import re # For potential regex validation

# --- Poll Option Schemas ---
class PollOptionCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=255, description="Text for the poll option, 1-255 characters.")

    @validator('text')
    def text_must_not_be_empty_or_whitespace(cls, value):
        if not value.strip():
            raise ValueError('Option text cannot be empty or only whitespace.')
        return value.strip() # Sanitize by stripping leading/trailing whitespace

class PollOption(PollOptionCreate): # Inherits text
    id: int
    votes: int = Field(0, ge=0, description="Number of votes for this option, must be non-negative.")

    class Config:
        from_attributes = True

# --- Base schema for common poll attributes ---
class PollBase(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000, description="The poll question, 3-1000 characters.")
    creator_display_name: Optional[str] = Field(
        None,
        min_length=2, # If provided, should be at least 2 chars
        max_length=50, # Reduced from 100 for brevity
        pattern=r"^[a-zA-Z0-9 _'-]*$", # Allow alphanumeric, space, underscore, hyphen, apostrophe
        description="Optional creator display name, 2-50 chars. Allows alphanumeric, space, underscore, hyphen, apostrophe."
    )
    allow_multiple_selections: bool = False
    voting_security_level: str = Field(
        "cookie_basic",  # Current default, can be changed to "none" if preferred
        pattern="^(none|cookie_basic|cookie_strict|ip_address)$", # ADDED "none"
        description="Security level for voting: 'none', 'cookie_basic', 'cookie_strict', or 'ip_address'."
    )
    is_public: bool = False
    # Note: modification_code is NOT in PollBase

    @validator('question')
    def question_must_not_be_empty_or_whitespace(cls, value):
        if not value.strip():
            raise ValueError('Question cannot be empty or only whitespace.')
        return value.strip() # Sanitize

    @validator('creator_display_name', pre=True, always=True)
    def sanitize_creator_display_name(cls, value):
        if value is not None:
            return value.strip()
        return value


# --- Schema for creating a new poll (request body) ---
class PollCreate(PollBase):
    options: List[PollOptionCreate] = Field(..., min_items=2, max_items=20, description="List of 2 to 20 poll options.")

    @model_validator(mode='after')
    def check_unique_option_texts(cls, values):
        # This validator runs after individual field validation
        # For Pydantic v2, model_validator replaces root_validator
        # The 'values' argument is the model instance itself in Pydantic v2
        # For Pydantic v1, it would be:
        # options = values.get('options')
        # if options:
        #     texts = [opt.text.lower().strip() for opt in options]
        #     if len(texts) != len(set(texts)):
        #         raise ValueError('Option texts must be unique within a poll (case-insensitive).')
        # return values
        
        # Pydantic v2 style:
        if values.options:
            texts: Set[str] = set()
            for option in values.options:
                # Assuming PollOptionCreate.text is already stripped by its own validator
                normalized_text = option.text.lower()
                if normalized_text in texts:
                    raise ValueError('Option texts must be unique within a poll (case-insensitive).')
                texts.add(normalized_text)
        return values


# --- Schema for publicly viewing a poll (omits modification_code) ---
class PollPublic(PollBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    options: List[PollOption] = [] # Uses the full PollOption schema

    class Config:
        from_attributes = True

# --- Schema for poll response when modification_code should be included (e.g., after creation) ---
class PollWithModificationCode(PollPublic): # Inherits all fields from PollPublic
    modification_code: str = Field(..., min_length=6, max_length=12, description="Modification code for the poll, 6-12 characters.") # Assuming a fixed length or range

    class Config:
        from_attributes = True

# --- Other existing schemas ---
class VoteRequest(BaseModel):
    selected_options: List[int] = Field(..., min_items=1, description="List of selected option IDs, at least one required.")
    # We could add max_items if allow_multiple_selections is False, but that's business logic
    # better handled in the endpoint based on the poll's settings.

# --- Schemas for Poll Update ---
# This schema is used within PollUpdate for options whose text is being updated.
class PollOptionTextUpdate(BaseModel): 
    id: int = Field(..., description="The ID of the option to update.")
    text: str = Field(..., min_length=1, max_length=255, description="New text for the poll option, 1-255 characters.")

    @validator('text')
    def text_update_must_not_be_empty_or_whitespace(cls, value):
        if not value.strip():
            raise ValueError('Option text cannot be empty or only whitespace.')
        return value.strip()

class PollUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=3, max_length=1000, description="New poll question, 3-1000 characters.")
    is_public: Optional[bool] = None
    allow_multiple_selections: Optional[bool] = None # You had this, it's reasonable to allow updating
    
    options_to_add: Optional[List[PollOptionCreate]] = Field(None, max_items=20, description="List of new options to add. Uses PollOptionCreate schema.")
    options_to_update: Optional[List[PollOptionTextUpdate]] = Field(None, max_items=20, description="List of existing options whose text needs to be updated.")
    option_ids_to_remove: Optional[List[int]] = Field(None, max_items=20, description="List of IDs of options to remove. Options should ideally have 0 votes to be removed (enforced in CRUD).")
    
    # modification_code is present in your existing schema for PollUpdate.
    # This means the client will send it in the body of the PUT request.
    # The endpoint will need to extract and verify it.
    modification_code: str = Field(..., min_length=6, max_length=12, description="Modification code for authentication, 6-12 characters.")

    @validator('question', pre=True, always=True)
    def question_update_must_not_be_empty_or_whitespace(cls, value):
        if value is not None:
            if not value.strip():
                raise ValueError('Question cannot be empty or only whitespace if provided.')
            return value.strip()
        return value
    
    # Consider adding a model_validator for more complex cross-field validation if needed, for example:
    # - Ensuring an option ID isn't in both options_to_update and option_ids_to_remove.
    # - Ensuring uniqueness of option texts after considering additions, updates, and non-removed existing options.
    #   This can also be handled robustly in the CRUD layer.

class PollDeleteRequest(BaseModel):
    modification_code: str = Field(..., min_length=6, max_length=12, description="Modification code for authentication, 6-12 characters.")

class VerifyModificationCodeRequest(BaseModel):
    modification_code: str = Field(..., min_length=6, max_length=12, description="Modification code to verify, 6-12 characters.")

class VerifyModificationCodeResponse(BaseModel):
    verified: bool
    detail: Optional[str] = None

# --- Schema for retrieving multiple polls by their IDs (for "Saved Polls" page) ---
class PollsByIdsRequest(BaseModel):
    poll_ids: List[UUID] = Field(..., min_items=1, max_items=50, description="List of 1 to 50 poll IDs to retrieve.")

# --- Schemas for Poll Edit History ---
class PollEditHistoryEntry(BaseModel):
    id: int
    poll_id: UUID
    edited_at: datetime
    field_changed: str = Field(..., description="Describes what was changed, e.g., 'question', 'option_text'.")
    option_id_changed: Optional[int] = Field(None, description="ID of the option that was changed, if applicable.")
    old_value: Optional[str] = Field(None, description="The value before the change.")
    new_value: Optional[str] = Field(None, description="The value after the change.")
    change_description: Optional[str] = Field(None, description="A more detailed description of the change, if applicable.")

    class Config:
        from_attributes = True
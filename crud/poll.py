from sqlalchemy.orm import Session, joinedload, selectinload # Added selectinload
from sqlalchemy import func, select, delete
from uuid import uuid4, UUID as UUID_TYPE
import random
import string
from typing import List, Optional, Tuple, Dict

# Import IndividualVote model AND PollEditHistory
from models import Poll, PollOption, IndividualVote, PollEditHistory # PollEditHistory should be here
# Ensure VoteRequest is imported from schemas
from schemas import (
    PollCreate,
    PollUpdate,
    PollsByIdsRequest,
    PollOptionCreate,
    PollOptionTextUpdate,
    VoteRequest # Make sure VoteRequest is in your schemas.py
)
from fastapi import status # Keep this if used, though not directly in the provided snippet
from core.logging_config import get_logger
from core import exceptions as exc

logger = get_logger(__name__)

# --- Predefined lists for random name generation ---
ADJECTIVES = [
    "Quick", "Clever", "Wise", "Happy", "Sunny", "Brave", "Calm", "Eager",
    "Gentle", "Jolly", "Keen", "Lively", "Merry", "Nice", "Proud", "Silly",
    "Witty", "Zany", "Sparkling", "Vivid", "Radiant", "Playful", "Dynamic"
]

NOUNS = [
    "Fox", "Owl", "Panda", "Tiger", "Lion", "Bear", "Wolf", "Eagle", "Hawk",
    "Robin", "Sparrow", "Badger", "Beaver", "Otter", "Quokka", "Koala",
    "Lemur", "Meerkat", "Penguin", "Dolphin", "Whale", "Unicorn", "Dragon"
]

def generate_random_display_name() -> str:
    """Generates a random 'Adjective Noun' display name."""
    adjective = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    return f"{adjective} {noun}"

def generate_modification_code(length: int = 8) -> str:
    """Generate a random alphanumeric modification code."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_voter_token() -> str:
    """Generates a unique voter token."""
    return str(uuid4())

def create_poll(db: Session, poll_data: PollCreate) -> Poll: # Renamed poll to poll_data
    """Create a new poll and save it to the database."""
    modification_code = generate_modification_code()

    creator_name = poll_data.creator_display_name
    if not creator_name or creator_name.strip() == "":
        creator_name = generate_random_display_name()
        logger.info("generated_random_creator_name", generated_name=creator_name) # Added log

    db_poll = Poll(
        id=uuid4(),
        question=poll_data.question,
        creator_display_name=creator_name,
        allow_multiple_selections=poll_data.allow_multiple_selections,
        voting_security_level=poll_data.voting_security_level,
        is_public=poll_data.is_public,
        modification_code=modification_code,
    )
    db.add(db_poll)
    # Commit here to get db_poll.id for options
    # It's often better to commit once at the end if possible, but for options needing poll_id,
    # an intermediate commit or flush might be necessary if not handled by relationship back_populates.
    # For simplicity here, we'll commit before adding options if poll_id is strictly needed.
    # Consider using db.flush() if you need the ID but want to defer the commit.
    try:
        db.commit()
        db.refresh(db_poll)
    except Exception as e: # Catch potential DB errors during commit
        db.rollback()
        logger.error(
            "db_create_poll_error",
            error_message=str(e),
            poll_question=poll_data.question, # Add relevant data
            exc_info=True
        )
        raise exc.QuickPollException(status_code=500, detail="Failed to create poll due to a database error.", code="DB_CREATE_POLL_ERROR")


    for option_data in poll_data.options:
        db_option = PollOption(text=option_data.text, poll_id=db_poll.id)
        db.add(db_option)
    try:
        db.commit()
        db.refresh(db_poll) # Refresh to get options loaded
        # Eagerly load options after creation if they are accessed immediately
        db.refresh(db_poll, ['options'])
    except Exception as e: # Catch potential DB errors during options commit
        db.rollback()
        logger.error(
            "db_create_options_error",
            error_message=str(e),
            poll_id=str(db_poll.id), # Add relevant data
            exc_info=True
        )
        # If the poll was created but options failed, the poll might exist without options.
        # Depending on desired atomicity, you might want to delete the poll here or handle differently.
        raise exc.QuickPollException(status_code=500, detail="Failed to create poll options due to a database error.", code="DB_CREATE_OPTIONS_ERROR")
    logger.info("poll_created_successfully", poll_id=str(db_poll.id), question=db_poll.question)
    return db_poll

def get_poll(db: Session, poll_id: UUID_TYPE) -> Poll | None:
    """Retrieve a poll by its ID."""
    # No specific logging needed here unless for debugging very low-level access
    return db.query(Poll).options(joinedload(Poll.options)).filter(Poll.id == poll_id).first()

def verify_modification_code(db: Session, poll_id: UUID_TYPE, provided_code: str) -> bool:
    """
    Verify if the provided modification code matches the poll's stored code.
    Returns True if the poll exists and the code matches, False otherwise.
    """
    db_poll = get_poll(db, poll_id) # Use the get_poll helper
    if not db_poll:
        # Log this attempt, as it might be an indicator of a client error or probing
        logger.warning(
            "verify_mod_code_poll_not_found",
            attempted_poll_id=str(poll_id)
        )
        return False
    
    is_match = db_poll.modification_code == provided_code
    if not is_match:
        logger.warning(
            "verify_mod_code_mismatch",
            poll_id=str(poll_id)
            # Do not log provided_code or db_poll.modification_code directly for security
        )
    return is_match

def update_poll(db: Session, poll_id: UUID_TYPE, poll_update_data: PollUpdate) -> Poll:
    """
    Update an existing poll. Allows editing question, options, and other attributes.
    Logs significant changes to PollEditHistory.
    """
    # Fetch the poll and its options eagerly.
    # Use selectinload for options if you anticipate accessing individual_votes_on_option per option later,
    # otherwise joinedload is fine.
    db_poll = db.query(Poll).options(
        joinedload(Poll.options).selectinload(PollOption.individual_votes_on_option), # Eager load votes for options
        # joinedload(Poll.edit_history) # Not typically needed when updating, but consider if you read it back immediately
    ).filter(Poll.id == poll_id).first()

    if not db_poll:
        raise exc.PollNotFoundException(poll_id=str(poll_id))

    if db_poll.modification_code != poll_update_data.modification_code:
        logger.warning("update_poll_invalid_mod_code", poll_id=str(poll_id))
        raise exc.InvalidModificationCodeException()

    changes_made_to_poll_object = False # Tracks direct changes to db_poll fields
    history_entries_to_add: List[PollEditHistory] = []

    # --- Helper to create history entries ---
    def _add_history_entry(field: str, old_val, new_val, option_id: Optional[int] = None, desc: Optional[str] = None):
        history_entries_to_add.append(
            PollEditHistory(
                poll_id=db_poll.id,
                field_changed=field,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                option_id_changed=option_id,
                change_description=desc
            )
        )
        logger.info(
            "poll_update_change_logged",
            poll_id=str(db_poll.id),
            field=field,
            old_value=str(old_val) if old_val is not None else "N/A",
            new_value=str(new_val) if new_val is not None else "N/A",
            option_id=option_id,
            description=desc
        )

    # --- Update Poll Question ---
    if poll_update_data.question is not None and db_poll.question != poll_update_data.question:
        old_question = db_poll.question
        db_poll.question = poll_update_data.question
        _add_history_entry("question", old_question, db_poll.question)
        changes_made_to_poll_object = True

    # --- Update is_public ---
    if poll_update_data.is_public is not None and db_poll.is_public != poll_update_data.is_public:
        old_is_public = db_poll.is_public
        db_poll.is_public = poll_update_data.is_public
        _add_history_entry("is_public", old_is_public, db_poll.is_public)
        changes_made_to_poll_object = True

    # --- Update allow_multiple_selections ---
    if poll_update_data.allow_multiple_selections is not None and \
       db_poll.allow_multiple_selections != poll_update_data.allow_multiple_selections:
        # PRD implies this can be changed. Consider implications if votes exist.
        # For now, allowing change and logging it.
        old_allow_multiple = db_poll.allow_multiple_selections
        db_poll.allow_multiple_selections = poll_update_data.allow_multiple_selections
        _add_history_entry("allow_multiple_selections", old_allow_multiple, db_poll.allow_multiple_selections)
        changes_made_to_poll_object = True

    # --- Process Option Updates, Additions, and Removals ---
    existing_options_map: Dict[int, PollOption] = {opt.id: opt for opt in db_poll.options}
    current_option_texts_lower: set[str] = {opt.text.lower() for opt in db_poll.options}

    # 1. Remove Options
    if poll_update_data.option_ids_to_remove:
        for opt_id_remove in poll_update_data.option_ids_to_remove:
            option_to_remove = existing_options_map.get(opt_id_remove)
            if not option_to_remove:
                logger.warning("update_poll_remove_non_existent_option", poll_id=str(db_poll.id), option_id=opt_id_remove)
                raise exc.InvalidRequestException(detail=f"Option ID {opt_id_remove} to remove not found in this poll.")

            # Check if the option has votes (by checking the length of individual_votes_on_option)
            if option_to_remove.individual_votes_on_option and len(option_to_remove.individual_votes_on_option) > 0:
                logger.warning("update_poll_remove_option_with_votes_denied", poll_id=str(db_poll.id), option_id=opt_id_remove, votes=len(option_to_remove.individual_votes_on_option))
                raise exc.PollUpdateNotAllowedException(detail=f"Cannot remove option ID {opt_id_remove} ('{option_to_remove.text}') as it has votes.")
            
            _add_history_entry("option_removed", option_to_remove.text, None, option_id=opt_id_remove, desc=f"Option '{option_to_remove.text}' (ID: {opt_id_remove}) removed.")
            current_option_texts_lower.discard(option_to_remove.text.lower())
            db.delete(option_to_remove) # Deleting from session
            del existing_options_map[opt_id_remove] # Remove from our map
            changes_made_to_poll_object = True # Indicates a structural change needing commit

    # 2. Update Existing Options' Text
    if poll_update_data.options_to_update:
        for opt_update_data in poll_update_data.options_to_update:
            option_to_edit = existing_options_map.get(opt_update_data.id)
            if not option_to_edit:
                logger.warning("update_poll_update_non_existent_option", poll_id=str(db_poll.id), option_id=opt_update_data.id)
                raise exc.InvalidRequestException(detail=f"Option ID {opt_update_data.id} to update not found in this poll.")

            if option_to_edit.text != opt_update_data.text:
                # Check for duplicate text among remaining and newly updated options
                # Temporarily remove old text, check new text, then add new text
                temp_current_texts = set(current_option_texts_lower)
                temp_current_texts.discard(option_to_edit.text.lower())
                if opt_update_data.text.lower() in temp_current_texts:
                    logger.warning("update_poll_duplicate_option_text_on_update", poll_id=str(db_poll.id), option_text=opt_update_data.text)
                    raise exc.DuplicateOptionTextException(text=opt_update_data.text)

                old_text = option_to_edit.text
                option_to_edit.text = opt_update_data.text
                _add_history_entry("option_text_updated", old_text, option_to_edit.text, option_id=option_to_edit.id)
                current_option_texts_lower.discard(old_text.lower())
                current_option_texts_lower.add(option_to_edit.text.lower())
                changes_made_to_poll_object = True

    # 3. Add New Options
    if poll_update_data.options_to_add:
        for opt_add_data in poll_update_data.options_to_add:
            if opt_add_data.text.lower() in current_option_texts_lower:
                logger.warning("update_poll_duplicate_option_text_on_add", poll_id=str(db_poll.id), option_text=opt_add_data.text)
                raise exc.DuplicateOptionTextException(text=opt_add_data.text)

            new_option = PollOption(
                poll_id=db_poll.id,
                text=opt_add_data.text,
                votes=0 # New options start with 0 votes
            )
            db.add(new_option)
            # We need the new_option.id for history logging.
            # Flushing the session will assign an ID to new_option without committing the transaction.
            db.flush() # Flush to get new_option.id
            _add_history_entry("option_added", None, new_option.text, option_id=new_option.id, desc=f"Option '{new_option.text}' added.")
            current_option_texts_lower.add(new_option.text.lower())
            # Add to db_poll.options so it's available if we refresh db_poll later
            # db_poll.options.append(new_option) # SQLAlchemy usually handles this via relationship
            changes_made_to_poll_object = True


    # --- Finalize ---
    if changes_made_to_poll_object or history_entries_to_add: # If any direct poll field changed or options changed
        db_poll.updated_at = func.now() # Manually set updated_at for the poll itself
        logger.info("poll_updated_with_changes", poll_id=str(db_poll.id), num_history_entries=len(history_entries_to_add))
        if history_entries_to_add:
            db.add_all(history_entries_to_add)
    else:
        logger.info("poll_update_no_effective_changes_made", poll_id=str(db_poll.id))
        # If no changes, we might not even need to commit, but for simplicity, we proceed.
        # The endpoint could return 304 Not Modified if desired and if no history entries.

    try:
        db.commit()
        db.refresh(db_poll)
        # Eagerly load options and history again as they might have changed
        db.refresh(db_poll, ['options', 'edit_history'])
    except exc.QuickPollException: # Re-raise known exceptions
        raise
    except Exception as e:
        db.rollback()
        logger.error("db_update_poll_commit_error", poll_id=str(db_poll.id), error_message=str(e), exc_info=True)
        raise exc.QuickPollException(status_code=500, detail="Failed to update poll due to a database error.", code="DB_UPDATE_POLL_ERROR")

    return db_poll

def get_polls_by_ids(db: Session, poll_ids: List[UUID_TYPE]) -> List[Poll]:
    """
    Retrieve multiple polls by a list of their IDs.
    Polls are returned in the order of the provided IDs, if found.
    """
    if not poll_ids:
        return []
    
    logger.debug("fetching_polls_by_ids", num_ids=len(poll_ids), poll_ids=[str(pid) for pid in poll_ids])

    # Fetch polls matching the provided IDs
    polls = db.query(Poll).options(joinedload(Poll.options)).filter(Poll.id.in_(poll_ids)).all()

    # Optional: If you want to return them in the same order as poll_ids
    polls_dict = {str(poll.id): poll for poll in polls}
    ordered_polls = [polls_dict[str(pid)] for pid in poll_ids if str(pid) in polls_dict]
    
    logger.debug("fetched_polls_by_ids_result", num_found=len(ordered_polls), requested_ids=len(poll_ids))
    return ordered_polls

def crud_vote_on_poll(
    db: Session,
    poll_id: UUID_TYPE,
    vote_request: VoteRequest,
    existing_voter_token: Optional[str] = None
) -> Tuple[Poll, Optional[str]]:
    """
    Handles casting or updating a vote on a poll using a voter token system.
    Returns the updated poll and a new voter token if one was generated.
    """
    poll = db.query(Poll).options(joinedload(Poll.options)).filter(Poll.id == poll_id).first()

    if not poll:
        logger.warning("vote_attempt_poll_not_found", poll_id=str(poll_id))
        raise exc.PollNotFoundException(poll_id=str(poll_id))

    if not poll.options: # Should ideally not happen if joinedload worked
        logger.error("poll_options_missing_in_vote", poll_id=str(poll_id))
        raise exc.QuickPollException(status_code=500, detail="Internal error: Poll data is inconsistent.", code="POLL_OPTIONS_UNEXPECTEDLY_NONE")

    # Validate selected option IDs
    valid_option_ids_in_poll = {opt.id for opt in poll.options}
    for selected_opt_id in vote_request.selected_options:
        if selected_opt_id not in valid_option_ids_in_poll:
            logger.warning(
                "vote_invalid_option_id",
                poll_id=str(poll_id),
                selected_option_id=selected_opt_id,
                valid_options=list(valid_option_ids_in_poll)
            )
            raise exc.InvalidVoteException(detail=f"Option ID {selected_opt_id} is not valid for this poll.")

    # Enforce single selection if not allowed
    if not poll.allow_multiple_selections and len(vote_request.selected_options) > 1:
        logger.warning(
            "vote_multiple_options_for_single_select_poll",
            poll_id=str(poll_id),
            num_selected=len(vote_request.selected_options)
        )
        raise exc.InvalidVoteException(detail="Multiple options selected for a poll that does not allow it.")
    
    if not vote_request.selected_options: # Should be caught by Pydantic min_items=1, but good to double check
        logger.warning("vote_no_options_selected", poll_id=str(poll_id))
        raise exc.InvalidVoteException(detail="No options were selected for voting.")


    token_to_use: str
    newly_generated_token: Optional[str] = None

    if existing_voter_token:
        token_to_use = existing_voter_token
        logger.info("vote_update_attempt", poll_id=str(poll_id), voter_token=token_to_use)
        # Find and delete previous votes by this token for this poll
        # And decrement vote counts on PollOption
        previous_individual_votes = db.execute(
            select(IndividualVote).where(
                IndividualVote.poll_id == poll_id,
                IndividualVote.voter_token == token_to_use
            )
        ).scalars().all()

        if previous_individual_votes:
            logger.info(
                "clearing_previous_votes",
                poll_id=str(poll_id),
                voter_token=token_to_use,
                num_previous_votes=len(previous_individual_votes)
            )
            for prev_vote in previous_individual_votes:
                # Find the PollOption to decrement its vote count
                option_to_decrement = db.get(PollOption, prev_vote.option_id) # Use db.get for PK lookup
                if option_to_decrement:
                    option_to_decrement.votes = max(0, option_to_decrement.votes - 1) # Ensure votes don't go below 0
                    logger.debug(
                        "decremented_vote_count",
                        poll_id=str(poll_id),
                        option_id=prev_vote.option_id,
                        new_count=option_to_decrement.votes
                    )
                db.delete(prev_vote)
            # It's good practice to flush changes if subsequent operations depend on them before commit
            # db.flush() # Optional: flush deletions and decrements
    else:
        token_to_use = generate_voter_token()
        newly_generated_token = token_to_use
        logger.info("new_vote_cast", poll_id=str(poll_id), new_voter_token=token_to_use)

    # Add new votes
    options_map = {opt.id: opt for opt in poll.options} # For quick lookup
    for selected_option_id in vote_request.selected_options:
        new_individual_vote = IndividualVote(
            poll_id=poll.id,
            option_id=selected_option_id,
            voter_token=token_to_use
        )
        db.add(new_individual_vote)

        # Increment vote count on PollOption
        option_to_increment = options_map.get(selected_option_id)
        if option_to_increment: # Should always be true due to validation above
            option_to_increment.votes += 1
            logger.debug(
                "incremented_vote_count",
                poll_id=str(poll_id),
                option_id=selected_option_id,
                new_count=option_to_increment.votes
            )
        else: # Should not happen if validation is correct
            logger.error("vote_option_not_found_during_increment", poll_id=str(poll_id), option_id=selected_option_id)


    try:
        db.commit()
        db.refresh(poll)
        # Eagerly load options again as their vote counts have changed
        db.refresh(poll, ['options'])
        # Also refresh individual_votes if you plan to return them or use them immediately
        # db.refresh(poll, ['individual_votes'])
    except Exception as e:
        db.rollback()
        logger.error(
            "db_vote_on_poll_error",
            poll_id=str(poll_id),
            voter_token=token_to_use,
            error_message=str(e),
            exc_info=True
        )
        raise exc.QuickPollException(status_code=500, detail="Failed to record vote due to a database error.", code="DB_VOTE_ERROR")

    logger.info(
        "vote_processed_successfully",
        poll_id=str(poll_id),
        voter_token=token_to_use,
        selected_options=vote_request.selected_options
    )
    return poll, newly_generated_token

# Remove or adapt the old 'some_vote_handling_function' if it exists
# def some_vote_handling_function(...):
#    pass

# At the end of the file, or grouped with other "get" functions

def get_poll_edit_history(db: Session, poll_id: UUID_TYPE) -> List[PollEditHistory]:
    """
    Retrieve all edit history entries for a given poll_id,
    ordered by the edit timestamp in descending order (most recent first).
    """
    # First, check if the poll itself exists to give a more specific error
    # if the poll_id is entirely invalid.
    db_poll = db.query(Poll.id).filter(Poll.id == poll_id).first()
    if not db_poll:
        logger.warning("get_poll_edit_history_poll_not_found", poll_id=str(poll_id))
        # We raise PollNotFoundException here so the endpoint can return a 404
        # if the poll doesn't exist, rather than an empty list for history.
        raise exc.PollNotFoundException(poll_id=str(poll_id))

    logger.debug("fetching_poll_edit_history", poll_id=str(poll_id))
    history_entries = (
        db.query(PollEditHistory)
        .filter(PollEditHistory.poll_id == poll_id)
        .order_by(PollEditHistory.edited_at.desc()) # Most recent edits first
        .all()
    )
    logger.debug("poll_edit_history_fetch_successful", poll_id=str(poll_id), count=len(history_entries))
    return history_entries
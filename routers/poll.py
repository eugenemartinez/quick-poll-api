from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Response, Cookie
from sqlalchemy.orm import Session # Ensure Session is imported
import models # Import models to access Poll model directly for the check
from sqlalchemy import or_, func, desc, asc # Import desc, asc
from typing import List, Optional
from uuid import UUID
from enum import Enum # Import Enum

from database import get_db
# MODIFIED: Import all necessary CRUD functions
from crud.poll import (
    create_poll as crud_create_poll,
    verify_modification_code as crud_verify_modification_code,
    update_poll as crud_update_poll,
    get_poll as crud_get_poll,
    get_polls_by_ids as crud_get_polls_by_ids,
    crud_vote_on_poll,
    get_poll_edit_history as crud_get_poll_edit_history # ADD THIS IMPORT
)
from schemas import (
    PollWithModificationCode,
    PollPublic,
    PollCreate,
    # PollOption, # Not directly used as a type hint in this file's endpoints
    VoteRequest,
    PollUpdate, 
    PollDeleteRequest,
    VerifyModificationCodeRequest,
    VerifyModificationCodeResponse,
    PollsByIdsRequest,
    PollEditHistoryEntry # This is already imported, which is good
)
import models
from core.limiter_config import limiter
from core import exceptions as exc # Import custom exceptions
from core.logging_config import get_logger # Import the new get_logger

logger = get_logger(__name__)

router = APIRouter()

VOTER_TOKEN_COOKIE_NAME = "qp_voter_token" # Define a constant for the cookie name

# Define an Enum for sort options
class PollSortOptions(str, Enum):
    updated_at_desc = "updated_at_desc"
    updated_at_asc = "updated_at_asc"
    created_at_desc = "created_at_desc"
    created_at_asc = "created_at_asc"
    question_asc = "question_asc"
    question_desc = "question_desc"
    total_votes_desc = "total_votes_desc" # New
    total_votes_asc = "total_votes_asc"   # New

@router.post("/", response_model=PollWithModificationCode, status_code=status.HTTP_201_CREATED)
@limiter.limit("50/day")
def create_poll_endpoint(request: Request, poll: PollCreate, db: Session = Depends(get_db)):
    logger.info("create_poll_request_received", question=poll.question, num_options=len(poll.options))
    # CRUD function will handle its own detailed logging
    created_poll = crud_create_poll(db, poll)
    logger.info("create_poll_request_successful", poll_id=str(created_poll.id))
    return created_poll

@router.get("/", response_model=List[PollPublic])
def list_polls(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Search term to filter polls by question or creator display name"),
    sort: Optional[PollSortOptions] = Query(
        PollSortOptions.total_votes_desc,
        description="Sort order for the polls"
    ),
    db: Session = Depends(get_db)
):
    logger.debug(
        "list_polls_request_received",
        skip=skip,
        limit=limit,
        search_term=search,
        sort_by=sort.value if sort else None
    )
    # Subquery to calculate total votes for each poll
    total_votes_subquery = (
        db.query(
            models.PollOption.poll_id,
            func.sum(models.PollOption.votes).label("calculated_total_votes"),
        )
        .group_by(models.PollOption.poll_id)
        .subquery()
    )

    # Base query, outer join with the subquery to get total votes
    query = db.query(models.Poll).outerjoin(
        total_votes_subquery, models.Poll.id == total_votes_subquery.c.poll_id
    ).filter(models.Poll.is_public == True)


    if search:
        search_term_like = f"%{search}%"
        query = query.filter(
            or_(
                models.Poll.question.ilike(search_term_like),
                models.Poll.creator_display_name.ilike(search_term_like)
            )
        )

    # Apply sorting
    if sort == PollSortOptions.updated_at_asc:
        query = query.order_by(models.Poll.updated_at.asc())
    elif sort == PollSortOptions.created_at_desc:
        query = query.order_by(models.Poll.created_at.desc())
    elif sort == PollSortOptions.created_at_asc:
        query = query.order_by(models.Poll.created_at.asc())
    elif sort == PollSortOptions.question_asc:
        query = query.order_by(func.lower(models.Poll.question).asc())
    elif sort == PollSortOptions.question_desc:
        query = query.order_by(func.lower(models.Poll.question).desc())
    elif sort == PollSortOptions.total_votes_asc:
        query = query.order_by(asc(func.coalesce(total_votes_subquery.c.calculated_total_votes, 0)))
    elif sort == PollSortOptions.total_votes_desc: # This will be the default if set above
        query = query.order_by(desc(func.coalesce(total_votes_subquery.c.calculated_total_votes, 0)))
    else: # Default to updated_at_desc if sort parameter is somehow None or an unexpected value (though Enum should prevent this)
        query = query.order_by(models.Poll.updated_at.desc())


    polls = (
        query
        .offset(skip)
        .limit(limit)
        .all()
    )
    logger.debug("list_polls_request_successful", num_polls_returned=len(polls))
    return polls

@router.get("/{poll_id}", response_model=PollPublic)
def get_poll_endpoint(poll_id: UUID, db: Session = Depends(get_db)):
    logger.debug("get_poll_request_received", poll_id=str(poll_id))
    poll = crud_get_poll(db, poll_id)
    if not poll:
        # Exception will be logged by the main handler
        raise exc.PollNotFoundException(poll_id=str(poll_id))
    logger.debug("get_poll_request_successful", poll_id=str(poll_id))
    return poll

# --- NEW ENDPOINT for Poll Edit History ---
@router.get("/{poll_id}/history", response_model=List[PollEditHistoryEntry])
def get_poll_history_endpoint(
    poll_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Retrieve the edit history for a specific poll.
    The poll must exist, but it does not need to be public to view its history
    (as history is inherently public as per PRD).
    """
    logger.info("get_poll_history_request_received", poll_id=str(poll_id))
    try:
        # The CRUD function already checks if the poll exists and raises PollNotFoundException
        history_entries = crud_get_poll_edit_history(db=db, poll_id=poll_id)
        logger.info("get_poll_history_request_successful", poll_id=str(poll_id), count=len(history_entries))
        return history_entries
    except exc.PollNotFoundException as e:
        # Logged by CRUD, re-raise to be handled by exception handler
        raise e
    except Exception as e_generic:
        logger.error(
            "unexpected_error_fetching_poll_history",
            poll_id=str(poll_id),
            error_message=str(e_generic),
            exc_info=True
        )
        # Use a more specific exception if available, or a generic one
        raise exc.QuickPollException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching the poll history.",
            code="POLL_HISTORY_UNEXPECTED_ERROR"
        )

@router.post("/{poll_id}/vote", response_model=PollPublic)
@limiter.limit("50/hour")
def vote_on_poll_endpoint(
    request: Request,
    response: Response,
    poll_id: UUID,
    vote: VoteRequest,
    db: Session = Depends(get_db),
    # Read the voter token from a cookie. It's optional.
    qp_voter_token_from_cookie: Optional[str] = Cookie(None, alias=VOTER_TOKEN_COOKIE_NAME) # Renamed for clarity
):
    logger.info(
        "vote_on_poll_request_received",
        poll_id=str(poll_id),
        num_selected_options=len(vote.selected_options),
        selected_options=[str(opt_id) for opt_id in vote.selected_options],
        existing_voter_token_present=bool(qp_voter_token_from_cookie)
    )

    # Fetch the poll first to check its security level
    db_poll_for_security_check = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    if not db_poll_for_security_check:
        # This will be caught by crud_vote_on_poll as well, but good to have an early exit
        raise exc.PollNotFoundException(poll_id=str(poll_id))

    token_to_pass_to_crud = qp_voter_token_from_cookie
    is_none_security = db_poll_for_security_check.voting_security_level == "none"

    if is_none_security:
        token_to_pass_to_crud = None # For "none" security, always treat as a new voter, ignore incoming cookie
        logger.info("vote_on_poll_none_security_level", poll_id=str(poll_id))


    try:
        updated_poll, newly_generated_token = crud_vote_on_poll(
            db=db,
            poll_id=poll_id,
            vote_request=vote,
            existing_voter_token=token_to_pass_to_crud # Pass potentially overridden token
        )

        # If a new token was generated AND security level is NOT "none", set the cookie.
        if newly_generated_token and not is_none_security:
            logger.info("setting_new_voter_token_cookie", poll_id=str(poll_id), voter_token=newly_generated_token)
            response.set_cookie(
                key=VOTER_TOKEN_COOKIE_NAME,
                value=newly_generated_token,
                httponly=True,
                samesite="lax",
                secure=False, # Set to True if HTTPS only
                max_age=60*60*24*365
            )
        elif newly_generated_token and is_none_security:
            logger.info("vote_on_poll_none_security_level_cookie_not_set", poll_id=str(poll_id))


        logger.info("vote_on_poll_request_successful", poll_id=str(updated_poll.id))
        return updated_poll

    except exc.QuickPollException as e:
        raise e
    except Exception as e_generic:
        logger.error(
            "unexpected_error_in_vote_endpoint",
            poll_id=str(poll_id),
            error_message=str(e_generic),
            exc_info=True
        )
        raise exc.QuickPollException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your vote.",
            code="VOTE_ENDPOINT_UNEXPECTED_ERROR"
        )

@router.post("/{poll_id}/verify-code/", response_model=VerifyModificationCodeResponse)
@limiter.limit("20/hour")
def verify_poll_modification_code_endpoint(
    request: Request,
    poll_id: UUID,
    verification_data: VerifyModificationCodeRequest,
    db: Session = Depends(get_db)
):
    logger.info("verify_mod_code_request_received", poll_id=str(poll_id))
    temp_poll = crud_get_poll(db, poll_id) # Check existence first
    if not temp_poll:
        # Exception will be logged by main handler
        raise exc.PollNotFoundException(poll_id=str(poll_id))

    is_verified = crud_verify_modification_code(db, poll_id, verification_data.modification_code)
    
    if not is_verified:
        logger.warning("verify_mod_code_failed", poll_id=str(poll_id))
        # The CRUD layer's verify_modification_code also logs the mismatch.
        # Raising this exception will be caught by the main handler.
        raise exc.InvalidModificationCodeException()
    
    logger.info("verify_mod_code_successful", poll_id=str(poll_id))
    return VerifyModificationCodeResponse(verified=True, detail="Modification code verified successfully.")


@router.put("/{poll_id}", response_model=PollPublic) # response_model is PollPublic
@limiter.limit("50/day")
def update_poll_endpoint(
    request: Request,
    poll_id: UUID,
    poll_update_data: PollUpdate, # <--- Uses the PollUpdate schema
    db: Session = Depends(get_db)
):
    logger.info("update_poll_request_received", poll_id=str(poll_id), update_data_keys=list(poll_update_data.model_dump(exclude_unset=True).keys()))
    try:
        # Calls the crud_update_poll function
        updated_poll = crud_update_poll(db=db, poll_id=poll_id, poll_update_data=poll_update_data)
        logger.info("update_poll_request_successful", poll_id=str(updated_poll.id))
        return updated_poll
    except exc.QuickPollException as e: # Catch our specific custom exceptions from CRUD
        # These are already logged in CRUD or will be by the main handler with their specific details
        raise e
    except HTTPException as e_http:
        logger.warning(
            "http_exception_in_update_poll_endpoint", # Should be rare if CRUD uses custom exceptions
            detail=e_http.detail,
            status_code=e_http.status_code,
            poll_id=str(poll_id)
        )
        raise e_http
    except Exception as e_generic:
        logger.error(
            "unexpected_error_updating_poll_endpoint", # Different event name from CRUD
            poll_id=str(poll_id),
            error_message=str(e_generic),
            exc_info=True
        )
        raise exc.QuickPollException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                     detail="An unexpected error occurred while updating the poll.",
                                     code="POLL_UPDATE_UNEXPECTED_ERROR")


@router.delete("/{poll_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("50/day")
def delete_poll_endpoint(
    request: Request,
    poll_id: UUID,
    delete_request: PollDeleteRequest,
    db: Session = Depends(get_db)
):
    logger.info("delete_poll_request_received", poll_id=str(poll_id))
    db_poll = crud_get_poll(db, poll_id)
    if not db_poll:
        raise exc.PollNotFoundException(poll_id=str(poll_id))

    if db_poll.modification_code != delete_request.modification_code:
        logger.warning("delete_poll_invalid_mod_code", poll_id=str(poll_id))
        raise exc.InvalidModificationCodeException()

    try:
        # First delete related IndividualVote entries if any (cascade might handle this, but explicit can be safer)
        db.query(models.IndividualVote).filter(models.IndividualVote.poll_id == poll_id).delete(synchronize_session=False)
        # Then delete PollOption entries
        db.query(models.PollOption).filter(models.PollOption.poll_id == poll_id).delete(synchronize_session=False)
        db.delete(db_poll)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("delete_poll_commit_error", poll_id=str(poll_id), error=str(e), exc_info=True)
        raise exc.QuickPollException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting poll.", code="POLL_DELETE_ERROR")

    logger.info("delete_poll_request_successful", poll_id=str(poll_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/saved/", response_model=List[PollPublic])
def get_saved_polls_endpoint(
    request: Request,
    polls_request: PollsByIdsRequest,
    db: Session = Depends(get_db)
):
    logger.debug(
        "get_saved_polls_request_received",
        num_poll_ids=len(polls_request.poll_ids) if polls_request.poll_ids else 0,
        poll_ids=[str(pid) for pid in polls_request.poll_ids] if polls_request.poll_ids else []
    )
    if not polls_request.poll_ids:
        logger.debug("get_saved_polls_no_ids_provided")
        return []

    db_polls = crud_get_polls_by_ids(db=db, poll_ids=polls_request.poll_ids)
    logger.debug("get_saved_polls_request_successful", num_polls_returned=len(db_polls))
    return db_polls
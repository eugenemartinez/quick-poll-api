from fastapi import HTTPException, status

class QuickPollException(HTTPException):
    """Base exception for this application."""
    def __init__(self, status_code: int, detail: str, code: str = None):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code # Optional application-specific error code

# --- Specific Application Exceptions ---

class PollNotFoundException(QuickPollException):
    def __init__(self, poll_id: str = None):
        detail = "Poll not found."
        if poll_id:
            detail = f"Poll with ID '{poll_id}' not found."
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail, code="POLL_NOT_FOUND")

class InvalidVoteException(QuickPollException):
    def __init__(self, detail: str = "Invalid vote."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail, code="INVALID_VOTE")

class ModificationCodeRequiredException(QuickPollException):
    def __init__(self, detail: str = "A valid modification code is required for this operation."):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail, code="MODIFICATION_CODE_REQUIRED")

class InvalidModificationCodeException(QuickPollException):
    def __init__(self, detail: str = "The provided modification code is invalid or does not match the poll."):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail, code="INVALID_MODIFICATION_CODE")

class NotAuthorizedError(QuickPollException):
    def __init__(self, detail: str = "You are not authorized to perform this action."):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail, code="NOT_AUTHORIZED")

class PollUpdateNotAllowedException(QuickPollException):
    def __init__(self, detail: str = "This poll cannot be updated due to its current state (e.g., has votes)."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail, code="POLL_UPDATE_NOT_ALLOWED")

class DuplicateOptionTextException(QuickPollException):
    def __init__(self, text: str, detail: str = None):
        if detail is None:
            detail = f"An option with the text '{text}' already exists or is being added in this update. Option text must be unique within a poll."
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail, code="DUPLICATE_OPTION_TEXT")

# You can add more custom exceptions as needed, e.g.:
# class UserAlreadyVotedException(QuickPollException):
#     def __init__(self, detail: str = "You have already voted on this poll."):
#         super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail, code="ALREADY_VOTED")

from database import engine, get_db
import models
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles # <--- IMPORT THIS
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import text
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from redis import Redis
from typing import Optional
from pydantic import BaseModel

from core.limiter_config import limiter
from core.config import settings
from core import exceptions as exc
from core.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None

app = FastAPI(
    title=settings.PROJECT_NAME,
    # --- ADD SWAGGER UI PARAMETERS ---
    # You can customize the default docs and redoc URLs if needed
    # docs_url="/docs",
    # redoc_url="/redoc",
    # openapi_url will be default /openapi.json if not specified
    # swagger_ui_css_url will be set after mounting static files
    swagger_ui_parameters={"syntaxHighlight.theme": "obsidian", "tryItOutEnabled": True}, # Example parameters
    swagger_ui_oauth2_redirect_url="/docs/oauth2-redirect", # Default, good to be explicit
)

# --- MOUNT STATIC FILES ---
# This makes files in the 'static' directory available under the '/static' URL path
app.mount("/static", StaticFiles(directory="static"), name="static") # <--- ADD THIS LINE

# --- SET CUSTOM SWAGGER UI CSS ---
# This tells FastAPI to use your custom CSS file for the /docs page.
# The URL must be the path from which the browser can fetch the CSS.
app.swagger_ui_css_url = "/static/custom_swagger.css" # <--- ADD THIS LINE


# --- Add CORS middleware ---
if settings.CORS_ALLOWED_ORIGINS:
    logger.info("cors_origins_configured", origins=settings.CORS_ALLOWED_ORIGINS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS, # Use the parsed list from settings
        allow_credentials=True, # Allows cookies to be included in cross-origin requests
        allow_methods=["*"],    # Allows all standard methods (GET, POST, PUT, DELETE, etc.)
        allow_headers=["*"],    # Allows all headers
    )
else:
    logger.warning("cors_origins_not_configured", message="CORS middleware not added as no origins are defined in settings.")


# Attach the limiter to the app's state
app.state.limiter = limiter

# Include the poll router
from routers import poll as poll_router
app.include_router(poll_router.router, prefix="/api/polls", tags=["Polls"]) # Changed prefix to match your previous setup


# --- Custom Exception Handlers ---

@app.exception_handler(exc.QuickPollException)
async def quick_poll_exception_handler(request: Request, exception: exc.QuickPollException):
    """Handles all custom exceptions inheriting from QuickPollException."""
    # This logger.error call is already in good structlog style
    logger.error(
        "application_error", # Event name
        detail=exception.detail,
        code=exception.code,
        status_code=exception.status_code,
        request_method=request.method,
        request_url=str(request.url)
    )
    return JSONResponse(
        status_code=exception.status_code,
        content=ErrorResponse(detail=exception.detail, code=exception.code).model_dump(exclude_none=True),
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc_val: RequestValidationError):
    """Handles Pydantic validation errors."""
    error_messages = []
    for error in exc_val.errors():
        field = " -> ".join(str(loc) for loc in error['loc'])
        message = error['msg']
        error_messages.append(f"Field '{field}': {message}") # Keep this for detail_str for now
    
    detail_str = "Validation error. " + " | ".join(error_messages)
    # This logger.warning call is already in good structlog style
    logger.warning(
        "validation_error", # Event name
        errors=[err for err in exc_val.errors()], # Pass the raw errors for more structure
        request_method=request.method,
        request_url=str(request.url),
        # Consider logging request body carefully due to size/sensitivity
        # request_body_preview=str(await request.body())[:200] # Example: log a preview
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(detail=detail_str, code="VALIDATION_ERROR").model_dump(exclude_none=True),
    )

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc_val: RateLimitExceeded):
    logger.warning(
        "rate_limit_exceeded", # Event name
        detail=exc_val.detail,
        request_method=request.method,
        request_url=str(request.url)
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=ErrorResponse(detail=f"Rate limit exceeded: {exc_val.detail}", code="RATE_LIMIT_EXCEEDED").model_dump(exclude_none=True),
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc_val: Exception):
    """Handles any other unhandled exceptions."""
    # This logger.error call is already in good structlog style
    logger.error(
        "unhandled_exception", # Event name
        exception_type=type(exc_val).__name__,
        error_message=str(exc_val),
        request_method=request.method,
        request_url=str(request.url),
        exc_info=True # This will include stack trace via structlog processors
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(detail="An unexpected internal server error occurred.", code="INTERNAL_SERVER_ERROR").model_dump(exclude_none=True),
    )


# --- Root Endpoint & Startup Event ---
@app.get("/")
# @limiter.limit("3/5 minutes")
def read_root(request: Request):
    try:
        # Test database connection
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            db_status = "OK" if result.scalar_one() == 1 else "NOT OK (Query Failed)"
    except OperationalError as e_db:
        logger.error("database_connection_failed", error=str(e_db), exc_info=True)
        db_status = "NOT OK (OperationalError)"
    except Exception as e_generic:
        logger.error("database_check_unexpected_error", error=str(e_generic), exc_info=True)
        db_status = "NOT OK (Unexpected Error)"


    return {
        "message": "Welcome to Quick Poll!",
        "database_connection": db_status
    }


@app.on_event("startup")
async def startup_event():
    # Initialize database tables - moved here
    try:
        models.Base.metadata.create_all(bind=engine)
        logger.info("database_tables_initialized_startup")
    except Exception as e_startup_db:
        logger.error("database_tables_initialization_failed_startup", error=str(e_startup_db), exc_info=True)

    # Test Redis connection on startup using settings
    redis_check_uri = settings.REDIS_URL # Use settings
    if redis_check_uri:
        try:
            redis_client = Redis.from_url(redis_check_uri)
            if redis_client.ping():
                logger.info("redis_connection_successful_startup", redis_url=settings.REDIS_URL) # Use settings.REDIS_URL for consistency
            else:
                logger.error("redis_connection_ping_failed_startup", redis_url=settings.REDIS_URL)
        except Exception as e_startup_redis:
            logger.error("redis_connection_failed_startup", error=str(e_startup_redis), redis_url=settings.REDIS_URL, exc_info=True)
    else:
        logger.warning("redis_url_not_found_startup_check")
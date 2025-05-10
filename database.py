import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from core.config import settings # Import the settings object

# Get the DATABASE_URL from the centralized settings
DATABASE_URL = settings.DATABASE_URL # Use the settings object

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the environment or .env file and is required.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
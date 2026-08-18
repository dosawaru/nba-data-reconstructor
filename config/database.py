import os 
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# load environment variables
load_dotenv()

# get database URL
DATABASE_URL = os.getenv("DATABASE_URL")

# create engine
# pool_size: maximum number of connections in the pool
# max_overflow: maximum number of connections to allow beyond the pool size
engine = create_engine(
    DATABASE_URL,
    pool_size= 10,
    max_overflow= 10,
    echo= True
)

# create session
SessionLocal = sessionmaker(bind= engine, autocommit= False, autoflush= False)
Session = SessionLocal

# create base class for all models for them to inherit from and be able to use the session
Base = declarative_base()

def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()
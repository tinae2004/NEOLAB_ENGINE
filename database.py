from sqlalchemy import create_engine, Column, String, Float, Integer
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./neolab.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    balance = Column(Float, default=0.0)

class InstanceDB(Base):
    __tablename__ = "instances"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    vast_instance_id = Column(String, unique=True, index=True)
    status = Column(String, default="provisioning")
    dph = Column(Float, default=0.0)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
# from database import Base
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Stage(Base):
    __tablename__ = "stages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

class SampleStage(Base):
    __tablename__ = "sample_stages"
    id = Column(Integer, primary_key=True, index=True)
    stage_id = Column(Integer, ForeignKey("stages.id"))
    name = Column(String)  # Name of the file or stage-specific identifier
    sra_code = Column(String, index=True)  # SRA code of the sample
    size = Column(String)  # Size of the sample
    status = Column(String)  # Status of the sample
    user_id = Column(Integer, ForeignKey("users.id"))  # User who owns the sample

    stage = relationship("Stage")
    user = relationship("User")

class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    sample_stage_id = Column(Integer, ForeignKey("sample_stages.id"))
    file_path = Column(String)
    file_type = Column(String)

    sample_stage = relationship("SampleStage", back_populates="files")

SampleStage.files = relationship("File", back_populates="sample_stage")
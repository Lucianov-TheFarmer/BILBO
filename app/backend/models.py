from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Sample(Base):
    __tablename__ = "samples"
    id = Column(Integer, primary_key=True, index=True)
    sra_code = Column(String, unique=True, index=True)
    size = Column(String)
    status = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))  # Add user_id field
    stages = relationship("SampleStage", back_populates="sample")  # Ensure relationship is defined

class Stage(Base):
    __tablename__ = "stages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

class SampleStage(Base):
    __tablename__ = "sample_stages"
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"))
    stage_id = Column(Integer, ForeignKey("stages.id"))

    sample = relationship("Sample", back_populates="stages")
    stage = relationship("Stage")

class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    sample_stage_id = Column(Integer, ForeignKey("sample_stages.id"))
    file_path = Column(String)
    file_type = Column(String)

    sample_stage = relationship("SampleStage", back_populates="files")

Sample.stages = relationship("SampleStage", back_populates="sample")
SampleStage.files = relationship("File", back_populates="sample_stage")
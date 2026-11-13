from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from ..schemas.common import PipelineStatus
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
    name = Column(String)
    sra_code = Column(String, index=True)
    size = Column(String)
    status = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))

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


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id = Column(String(64), primary_key=True, index=True)
    stage = Column(String(64), index=True, nullable=False)
    status = Column(String(32), index=True, nullable=False, default=PipelineStatus.PENDING.value)
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    artifacts = relationship("Artifact", back_populates="job", cascade="all, delete-orphan")


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(64), ForeignKey("pipeline_jobs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(64), nullable=False, default="file")
    path = Column(String, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job = relationship("PipelineJob", back_populates="artifacts")
    user = relationship("User")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(128), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    stage = Column(String(64), nullable=True)
    job_id = Column(String(64), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User")


class AnalysisDesign(Base):
    __tablename__ = "analysis_designs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    config = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    config = Column(JSON, nullable=False)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    steps = relationship("PipelineStep", back_populates="run", cascade="all, delete-orphan")


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"
    __table_args__ = (UniqueConstraint("run_id", "sample", "stage", name="uq_pipeline_step"),)

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    sample = Column(String(181), nullable=False)
    stage = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    job_id = Column(String(64), ForeignKey("pipeline_jobs.id"))
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    run = relationship("PipelineRun", back_populates="steps")

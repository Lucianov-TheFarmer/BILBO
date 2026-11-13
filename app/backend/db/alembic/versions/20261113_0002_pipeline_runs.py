"""Persist automatic pipeline runs and statistical designs.

Revision ID: 20261113_0002
Revises: 20260215_0001
"""

from alembic import op
import sqlalchemy as sa

revision = "20261113_0002"
down_revision = "20260215_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("analysis_designs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_analysis_designs_user_id", "analysis_designs", ["user_id"], unique=True)
    op.create_table("pipeline_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.create_index("ix_pipeline_runs_user_id", "pipeline_runs", ["user_id"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])
    op.create_table("pipeline_steps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("sample", sa.String(181), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("pipeline_jobs.id")),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "sample", "stage", name="uq_pipeline_step"))
    op.create_index("ix_pipeline_steps_run_id", "pipeline_steps", ["run_id"])
    op.create_index("ix_pipeline_steps_status", "pipeline_steps", ["status"])


def downgrade():
    op.drop_table("pipeline_steps")
    op.drop_table("pipeline_runs")
    op.drop_table("analysis_designs")

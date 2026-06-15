"""Add review tasks.

Revision ID: 0002_review_tasks
Revises: 0001_embeddings
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_review_tasks"
down_revision: str | None = "0001_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.Integer(),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'medium'"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_review_tasks_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'dismissed')",
            name="ck_review_tasks_status",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'ai_suggested')",
            name="ck_review_tasks_source",
        ),
    )
    op.create_index(
        "ix_review_tasks_document_id",
        "review_tasks",
        ["document_id"],
    )
    op.create_index(
        "ix_review_tasks_chunk_id",
        "review_tasks",
        ["chunk_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_tasks_chunk_id", table_name="review_tasks")
    op.drop_index("ix_review_tasks_document_id", table_name="review_tasks")
    op.drop_table("review_tasks")

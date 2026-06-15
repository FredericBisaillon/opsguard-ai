"""Add audit events.

Revision ID: 0003_audit_events
Revises: 0002_review_tasks
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_audit_events"
down_revision: str | None = "0002_review_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "review_task_id",
            sa.Integer(),
            sa.ForeignKey("review_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'review_task_created', "
            "'review_task_dismissed', "
            "'ai_review_task_suggested', "
            "'ai_review_task_created', "
            "'ai_review_task_rejected', "
            "'ai_review_no_suggestion', "
            "'rag_prompt_injection_detected'"
            ")",
            name="ck_audit_events_event_type",
        ),
        sa.CheckConstraint(
            "actor_type IN ('system', 'human', 'ai')",
            name="ck_audit_events_actor_type",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'ai', 'api', 'system')",
            name="ck_audit_events_source",
        ),
        sa.CheckConstraint(
            "status IN ('success', 'rejected', 'failed', 'info')",
            name="ck_audit_events_status",
        ),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_document_id", "audit_events", ["document_id"])
    op.create_index(
        "ix_audit_events_review_task_id",
        "audit_events",
        ["review_task_id"],
    )
    op.create_index("ix_audit_events_source", "audit_events", ["source"])
    op.create_index("ix_audit_events_status", "audit_events", ["status"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_status", table_name="audit_events")
    op.drop_index("ix_audit_events_source", table_name="audit_events")
    op.drop_index("ix_audit_events_review_task_id", table_name="audit_events")
    op.drop_index("ix_audit_events_document_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_table("audit_events")

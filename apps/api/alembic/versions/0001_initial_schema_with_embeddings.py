"""Initial schema with pgvector embeddings.

Revision ID: 0001_embeddings
Revises:
Create Date: 2026-06-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_embeddings"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            source_type VARCHAR(50) NOT NULL,
            source_path TEXT NOT NULL,
            status VARCHAR(20) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL
                REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            character_count INTEGER NOT NULL,
            section_title VARCHAR(255),
            start_char INTEGER,
            end_char INTEGER,
            embedding vector(1536),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_document_chunks_document_id_chunk_index
                UNIQUE (document_id, chunk_index)
        )
        """
    )

    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS embedding vector(1536)
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_document_chunks_document_id_chunk_index'
            ) THEN
                ALTER TABLE document_chunks
                ADD CONSTRAINT uq_document_chunks_document_id_chunk_index
                UNIQUE (document_id, chunk_index);
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id
        ON document_chunks (document_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_chunks")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP EXTENSION IF EXISTS vector")

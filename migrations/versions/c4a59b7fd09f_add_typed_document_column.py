"""add typed document column

Revision ID: c4a59b7fd09f
Revises: e40f406e001b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a59b7fd09f"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "e40f406e001b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Add the new typed column.
    op.add_column(
        "documents",
        sa.Column("document", sa.Text(), nullable=True),
    )

    # 2. Backfill existing values from JSONB metadata.
    op.execute(
        """
        UPDATE documents
        SET document = metadata ->> 'document'
        WHERE metadata ? 'document'
        """
    )

    # 3. Create a B-tree index for faster document filtering.
    op.create_index(
        "ix_documents_document",
        "documents",
        ["document"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ix_documents_document", table_name="documents")
    op.drop_column("documents", "document")

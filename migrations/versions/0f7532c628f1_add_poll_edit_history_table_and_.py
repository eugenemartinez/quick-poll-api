"""add_poll_edit_history_table_and_relations

Revision ID: 0f7532c628f1
Revises: 13bfcd71ace1
Create Date: 2025-05-10 14:00:55.591600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f7532c628f1'
down_revision: Union[str, None] = '13bfcd71ace1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

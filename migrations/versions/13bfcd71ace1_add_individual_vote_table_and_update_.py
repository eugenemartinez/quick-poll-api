"""add_individual_vote_table_and_update_poll_relations

Revision ID: 13bfcd71ace1
Revises: 0f263cfef472
Create Date: 2025-05-10 11:25:42.634044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13bfcd71ace1'
down_revision: Union[str, None] = '0f263cfef472'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

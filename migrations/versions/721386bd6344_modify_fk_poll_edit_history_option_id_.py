"""modify_fk_poll_edit_history_option_id_ondelete_set_null

Revision ID: 721386bd6344
Revises: e7d87686b4d9
Create Date: 2025-05-10 15:06:29.952271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '721386bd6344'
down_revision: Union[str, None] = 'e7d87686b4d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The name of the existing foreign key constraint from the error message
original_constraint_name = 'poll_edit_history_option_id_changed_fkey'
# A new, descriptive name for the constraint we are creating
new_constraint_name = 'fk_peh_option_id_poll_option_id_set_null'


def upgrade() -> None:
    # Drop the existing foreign key constraint
    op.drop_constraint(
        constraint_name=original_constraint_name,
        table_name='poll_edit_history',
        type_='foreignkey'
    )
    # Create the new foreign key constraint with ON DELETE SET NULL
    op.create_foreign_key(
        constraint_name=new_constraint_name,
        source_table='poll_edit_history',
        referent_table='poll_option',
        local_cols=['option_id_changed'],
        remote_cols=['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Drop the new foreign key constraint
    op.drop_constraint(
        constraint_name=new_constraint_name,
        table_name='poll_edit_history',
        type_='foreignkey'
    )
    # Recreate the original foreign key constraint (without ON DELETE SET NULL)
    op.create_foreign_key(
        constraint_name=original_constraint_name,
        source_table='poll_edit_history',
        referent_table='poll_option',
        local_cols=['option_id_changed'],
        remote_cols=['id']
        # Default ondelete is NO ACTION or RESTRICT, which was the original behavior
    )

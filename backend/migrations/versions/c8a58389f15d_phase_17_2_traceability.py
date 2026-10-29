"""phase_17_2_traceability

Revision ID: c8a58389f15d
Revises: 3f79c09500eb
Create Date: 2026-09-27 12:07:42.100989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8a58389f15d'
down_revision: Union[str, Sequence[str], None] = '3f79c09500eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('metric_results') as batch_op:
        batch_op.add_column(sa.Column('trial_id', sa.String(), nullable=True))
        batch_op.create_foreign_key('fk_metric_results_trial_id', 'experiment_trials', ['trial_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('metric_results') as batch_op:
        batch_op.drop_constraint('fk_metric_results_trial_id', type_='foreignkey')
        batch_op.drop_column('trial_id')

"""add component_patterns to design_systems

Revision ID: a1b2c3d4e5f6
Revises: 845b2aa42ed8
Create Date: 2026-04-08 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '845b2aa42ed8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('design_systems') as batch_op:
        batch_op.add_column(sa.Column('component_patterns', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('design_systems') as batch_op:
        batch_op.drop_column('component_patterns')

"""drop slide_templates from design_systems

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-08 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('design_systems') as batch_op:
        batch_op.drop_column('slide_templates')


def downgrade():
    with op.batch_alter_table('design_systems') as batch_op:
        batch_op.add_column(sa.Column('slide_templates', sa.JSON(), nullable=True))

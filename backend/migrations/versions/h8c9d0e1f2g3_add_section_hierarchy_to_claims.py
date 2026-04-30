"""add section_hierarchy to claims

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h8c9d0e1f2g3'
down_revision = 'g7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('section_hierarchy', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_column('section_hierarchy')

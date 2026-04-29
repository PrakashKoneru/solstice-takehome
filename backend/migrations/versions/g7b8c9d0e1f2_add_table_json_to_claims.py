"""add table_json to claims

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('table_json', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_column('table_json')

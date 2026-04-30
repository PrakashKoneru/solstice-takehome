"""add embedding to claims

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i9d0e1f2g3h4'
down_revision = 'h8c9d0e1f2g3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('embedding', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_column('embedding')

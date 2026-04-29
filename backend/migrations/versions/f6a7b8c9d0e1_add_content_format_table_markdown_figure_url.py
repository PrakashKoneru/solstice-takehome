"""add content_format, table_markdown, figure_url to claims

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_format', sa.String(length=16), nullable=False, server_default='text'))
        batch_op.add_column(sa.Column('table_markdown', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('figure_url', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_column('figure_url')
        batch_op.drop_column('table_markdown')
        batch_op.drop_column('content_format')

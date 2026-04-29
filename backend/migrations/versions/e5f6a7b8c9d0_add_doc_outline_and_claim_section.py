"""add doc_outline to knowledge_items and section to claims

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('knowledge_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('doc_outline', sa.JSON(), nullable=True))

    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('section', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_column('section')

    with op.batch_alter_table('knowledge_items', schema=None) as batch_op:
        batch_op.drop_column('doc_outline')

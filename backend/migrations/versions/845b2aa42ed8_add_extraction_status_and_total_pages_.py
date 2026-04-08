"""add extraction_status and total_pages to knowledge_items

Revision ID: 845b2aa42ed8
Revises: 98a31ea2cc6e
Create Date: 2026-04-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '845b2aa42ed8'
down_revision = '98a31ea2cc6e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('knowledge_items', sa.Column('extraction_status', sa.String(length=20), server_default='pending'))
    op.add_column('knowledge_items', sa.Column('total_pages', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('knowledge_items', 'total_pages')
    op.drop_column('knowledge_items', 'extraction_status')

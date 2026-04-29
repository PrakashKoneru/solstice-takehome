"""add page_number to design_system_assets

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('design_system_assets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('page_number', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('design_system_assets', schema=None) as batch_op:
        batch_op.drop_column('page_number')

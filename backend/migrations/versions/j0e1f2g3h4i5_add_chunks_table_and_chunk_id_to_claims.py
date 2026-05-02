"""add chunks table and chunk_id to claims

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-05-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j0e1f2g3h4i5'
down_revision = 'i9d0e1f2g3h4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('chunks',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('knowledge_id', sa.Integer(), nullable=False),
        sa.Column('headings', sa.JSON(), nullable=True),
        sa.Column('serialized_text', sa.Text(), nullable=True),
        sa.Column('element_types', sa.JSON(), nullable=True),
        sa.Column('has_table', sa.Boolean(), nullable=True, default=False),
        sa.Column('has_figure', sa.Boolean(), nullable=True, default=False),
        sa.Column('page_start', sa.Integer(), nullable=True),
        sa.Column('page_end', sa.Integer(), nullable=True),
        sa.Column('embedding', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['knowledge_id'], ['knowledge_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chunk_id', sa.String(length=64), nullable=True))
        batch_op.create_foreign_key('fk_claims_chunk_id', 'chunks', ['chunk_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_constraint('fk_claims_chunk_id', type_='foreignkey')
        batch_op.drop_column('chunk_id')

    op.drop_table('chunks')

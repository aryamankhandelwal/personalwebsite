"""Add tracker_companies table

Revision ID: 33433ec83de6
Revises: eacadc70d089
Create Date: 2026-04-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33433ec83de6'
down_revision: Union[str, Sequence[str], None] = 'eacadc70d089'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tracker_companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('alpha', sa.Text(), nullable=True),
        sa.Column('founders', sa.Text(), nullable=True),
        sa.Column('stage', sa.Text(), nullable=True),
        sa.Column('notable_investors', sa.Text(), nullable=True),
        sa.Column('website', sa.Text(), nullable=True),
        sa.Column('sector', sa.Text(), nullable=False),
        sa.Column('region', sa.Text(), nullable=True),
        sa.Column(
            'is_featured',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
        sa.Column(
            'is_archived',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
        sa.Column(
            'date_added',
            sa.Date(),
            server_default=sa.text('CURRENT_DATE'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_tracker_companies_id'),
        'tracker_companies',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_tracker_companies_id'), table_name='tracker_companies')
    op.drop_table('tracker_companies')

"""Add tenant print_clause field

Revision ID: p7q8r9s0t1u2
Revises: o6p7q8r9s0t1
Create Date: 2026-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p7q8r9s0t1u2'
down_revision = 'o6p7q8r9s0t1'
branch_labels = None
depends_on = None


def upgrade():
    # Add print_clause column to tenant table
    op.add_column('tenant', sa.Column(
        'print_clause',
        sa.Text(),
        nullable=True,
        server_default='Uređaj se čuva 30 dana od obaveštenja o završetku popravke. Nakon isteka navedenog roka servis ne odgovara za uređaj. Garancija važi od datuma preuzimanja uređaja.'
    ))


def downgrade():
    op.drop_column('tenant', 'print_clause')
"""Add color fields to supplier_listing and service_ticket.

Revision ID: v577_add_color_fields
Revises: v576_supplier_rating_percentage
Create Date: 2026-02-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'v577_add_color_fields'
down_revision = 'v576_supplier_rating_percentage'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('supplier_listing', sa.Column('color', sa.String(50)))
    op.add_column('service_ticket', sa.Column('device_color', sa.String(50)))


def downgrade():
    op.drop_column('service_ticket', 'device_color')
    op.drop_column('supplier_listing', 'color')

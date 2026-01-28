"""Make prezime optional in TenantUser and ServiceRepresentative

Revision ID: v309_make_prezime_optional
Revises: v308a_audit_fixes
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v309_make_prezime_optional'
down_revision = 'v308a_audit_fixes'
branch_labels = None
depends_on = None


def upgrade():
    # Make prezime nullable in tenant_user
    op.alter_column('tenant_user', 'prezime',
                    existing_type=sa.String(50),
                    nullable=True)

    # Make prezime nullable in service_representative
    op.alter_column('service_representative', 'prezime',
                    existing_type=sa.String(50),
                    nullable=True)


def downgrade():
    # Revert prezime to NOT NULL in tenant_user
    # First, update any NULLs to empty string
    op.execute("UPDATE tenant_user SET prezime = '' WHERE prezime IS NULL")
    op.alter_column('tenant_user', 'prezime',
                    existing_type=sa.String(50),
                    nullable=False)

    # Revert prezime to NOT NULL in service_representative
    op.execute("UPDATE service_representative SET prezime = '' WHERE prezime IS NULL")
    op.alter_column('service_representative', 'prezime',
                    existing_type=sa.String(50),
                    nullable=False)

"""Add tenant login system - login_secret and username

Revision ID: v3w4x5y6z7a8
Revises: u2v3w4x5y6z7
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa
import secrets


# revision identifiers, used by Alembic.
revision = 'v3w4x5y6z7a8'
down_revision = 'u2v3w4x5y6z7'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Tenant: dodaj login_secret (nullable prvo)
    op.add_column('tenant', sa.Column('login_secret', sa.String(32), nullable=True))

    # 2. TenantUser: dodaj username (nullable prvo)
    op.add_column('tenant_user', sa.Column('username', sa.String(50), nullable=True))

    # 3. Popuni postojeće username-ove iz email-a (deo pre @)
    op.execute("""
        UPDATE tenant_user
        SET username = SPLIT_PART(email, '@', 1)
        WHERE username IS NULL AND email IS NOT NULL
    """)

    # 4. Popuni login_secret za postojeće tenante
    # Koristimo SQL funkciju za generisanje random stringa
    op.execute("""
        UPDATE tenant
        SET login_secret = SUBSTRING(MD5(RANDOM()::TEXT || id::TEXT) FROM 1 FOR 22)
        WHERE login_secret IS NULL
    """)

    # 5. Postavi NOT NULL constraints
    op.alter_column('tenant_user', 'username', nullable=False)
    op.alter_column('tenant', 'login_secret', nullable=False)

    # 6. Email postaje nullable
    op.alter_column('tenant_user', 'email', nullable=True)

    # 7. Kreiraj unique indekse
    op.create_unique_constraint('uq_tenant_user_username', 'tenant_user', ['tenant_id', 'username'])
    op.create_unique_constraint('uq_tenant_login_secret', 'tenant', ['login_secret'])


def downgrade():
    # Ukloni constraints
    op.drop_constraint('uq_tenant_login_secret', 'tenant', type_='unique')
    op.drop_constraint('uq_tenant_user_username', 'tenant_user', type_='unique')

    # Email ponovo NOT NULL
    op.alter_column('tenant_user', 'email', nullable=False)

    # Ukloni kolone
    op.drop_column('tenant', 'login_secret')
    op.drop_column('tenant_user', 'username')
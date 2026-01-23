"""Add employee dossier fields to TenantUser

Revision ID: w4x5y6z7a8b9
Revises: v3w4x5y6z7a8
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'w4x5y6z7a8b9'
down_revision = 'v3w4x5y6z7a8'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if column exists in table"""
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
        )
    """), {'table': table_name, 'column': column_name})
    return result.scalar()


def upgrade():
    # Adresa stanovanja
    if not column_exists('tenant_user', 'adresa'):
        op.add_column('tenant_user', sa.Column('adresa', sa.String(200), nullable=True))

    # Broj lične karte
    if not column_exists('tenant_user', 'broj_licne_karte'):
        op.add_column('tenant_user', sa.Column('broj_licne_karte', sa.String(20), nullable=True))

    # Datum početka radnog odnosa
    if not column_exists('tenant_user', 'pocetak_radnog_odnosa'):
        op.add_column('tenant_user', sa.Column('pocetak_radnog_odnosa', sa.Date(), nullable=True))

    # Tip ugovora (enum)
    if not column_exists('tenant_user', 'ugovor_tip'):
        # Kreiraj enum tip ako ne postoji
        tip_ugovora = sa.Enum('NEODREDJENO', 'ODREDJENO', name='tipugovora')
        tip_ugovora.create(op.get_bind(), checkfirst=True)
        op.add_column('tenant_user', sa.Column('ugovor_tip', tip_ugovora, nullable=True))

    # Trajanje ugovora u mesecima (za određeno)
    if not column_exists('tenant_user', 'ugovor_trajanje_meseci'):
        op.add_column('tenant_user', sa.Column('ugovor_trajanje_meseci', sa.Integer(), nullable=True))

    # Tip plate (enum)
    if not column_exists('tenant_user', 'plata_tip'):
        # Kreiraj enum tip ako ne postoji
        tip_plate = sa.Enum('FIKSNO', 'DNEVNICA', name='tipplate')
        tip_plate.create(op.get_bind(), checkfirst=True)
        op.add_column('tenant_user', sa.Column('plata_tip', tip_plate, nullable=True))

    # Iznos plate/dnevnice
    if not column_exists('tenant_user', 'plata_iznos'):
        op.add_column('tenant_user', sa.Column('plata_iznos', sa.Numeric(12, 2), nullable=True))

    # Napomena
    if not column_exists('tenant_user', 'napomena'):
        op.add_column('tenant_user', sa.Column('napomena', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('tenant_user', 'napomena')
    op.drop_column('tenant_user', 'plata_iznos')
    op.drop_column('tenant_user', 'plata_tip')
    op.drop_column('tenant_user', 'ugovor_trajanje_meseci')
    op.drop_column('tenant_user', 'ugovor_tip')
    op.drop_column('tenant_user', 'pocetak_radnog_odnosa')
    op.drop_column('tenant_user', 'broj_licne_karte')
    op.drop_column('tenant_user', 'adresa')

    # Drop enum types
    sa.Enum(name='tipugovora').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='tipplate').drop(op.get_bind(), checkfirst=True)
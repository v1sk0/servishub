"""Backfill location data for existing tenants

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-27

Task-003: Backfill migracija
- Postavi LocationStatus = ACTIVE za sve postojeće lokacije
- Postavi is_primary na najstariju lokaciju po tenantu
- Postavi current_location_id = primary za sve korisnike
- Kreiraj UserLocation zapise za sve existing parove
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Postavi LocationStatus = ACTIVE za sve lokacije bez statusa
    op.execute("UPDATE service_location SET status = 'ACTIVE' WHERE status IS NULL")

    # 2. Osigurai da svaki tenant ima tačno 1 primary lokaciju (najstarija)
    # Prvo resetuj sve na false, pa postavi najstariju
    op.execute("""
        WITH ranked AS (
            SELECT id, tenant_id,
                   ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY created_at) as rn
            FROM service_location WHERE status = 'ACTIVE'
        )
        UPDATE service_location SET is_primary = (
            service_location.id IN (SELECT id FROM ranked WHERE rn = 1)
        )
        WHERE tenant_id IN (
            SELECT tenant_id FROM service_location
            GROUP BY tenant_id
            HAVING COUNT(*) FILTER (WHERE is_primary = TRUE) != 1
        )
    """)

    # 3. Postavi current_location_id = primary za korisnike bez lokacije
    op.execute("""
        UPDATE tenant_user tu SET current_location_id = (
            SELECT sl.id FROM service_location sl
            WHERE sl.tenant_id = tu.tenant_id AND sl.is_primary = TRUE
            LIMIT 1
        ) WHERE tu.current_location_id IS NULL
    """)

    # 4. Kreiraj UserLocation zapise za sve user-location parove koji ne postoje
    op.execute("""
        INSERT INTO user_location (user_id, location_id, is_active, is_primary, can_manage, assigned_at, created_at)
        SELECT tu.id, sl.id, TRUE, sl.is_primary, FALSE, NOW(), NOW()
        FROM tenant_user tu
        JOIN service_location sl ON sl.tenant_id = tu.tenant_id AND sl.status = 'ACTIVE'
        WHERE NOT EXISTS (
            SELECT 1 FROM user_location ul
            WHERE ul.user_id = tu.id AND ul.location_id = sl.id
        )
    """)


def downgrade():
    # NE brišemo podatke — backfill je safe, downgrade je no-op
    pass

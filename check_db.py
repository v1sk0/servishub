"""Check database state for migration issues."""
from app.extensions import db
from app import create_app

app = create_app()
with app.app_context():
    # Check if part_order_request table exists
    result = db.session.execute(db.text("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename = 'part_order_request'
    """)).fetchall()
    print(f"part_order_request table exists: {len(result) > 0}")

    # Check existing indexes
    result = db.session.execute(db.text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'part_order_request'
    """)).fetchall()
    print(f"Indexes on part_order_request: {[r[0] for r in result]}")

    # Check for orphan index ix_part_order_status
    result = db.session.execute(db.text("""
        SELECT indexname, tablename FROM pg_indexes
        WHERE indexname = 'ix_part_order_status'
    """)).fetchall()
    print(f"ix_part_order_status exists: {result}")

    # Check ALL indexes with 'part_order' in name
    result = db.session.execute(db.text("""
        SELECT indexname, tablename FROM pg_indexes
        WHERE indexname LIKE '%part_order%'
    """)).fetchall()
    print(f"All part_order indexes: {result}")

    # Check marketplace_order_message table
    result = db.session.execute(db.text("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename = 'marketplace_order_message'
    """)).fetchall()
    print(f"marketplace_order_message table exists: {len(result) > 0}")

    # Check alembic version (correct column name)
    result = db.session.execute(db.text("""
        SELECT version_num FROM alembic_version
    """)).fetchall()
    print(f"Alembic version: {[r[0] for r in result]}")

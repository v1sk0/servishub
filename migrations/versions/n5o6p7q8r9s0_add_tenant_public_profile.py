"""Add tenant_public_profile table for public website

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-01-18 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'n5o6p7q8r9s0'
down_revision = 'm4n5o6p7q8r9'
branch_labels = None
depends_on = None


def upgrade():
    # Kreiraj tenant_public_profile tabelu
    op.create_table('tenant_public_profile',
        # Primarni ključ
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),

        # Vidljivost
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),

        # Osnovni podaci
        sa.Column('display_name', sa.String(length=200), nullable=True),
        sa.Column('tagline', sa.String(length=300), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),

        # Kontakt
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('phone_secondary', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=100), nullable=True),
        sa.Column('address', sa.String(length=300), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('postal_code', sa.String(length=20), nullable=True),
        sa.Column('maps_url', sa.String(length=500), nullable=True),
        sa.Column('maps_embed_url', sa.String(length=500), nullable=True),

        # Radno vreme
        sa.Column('working_hours', sa.JSON(), nullable=True),

        # Branding
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('cover_image_url', sa.String(length=500), nullable=True),
        sa.Column('primary_color', sa.String(length=7), nullable=True, server_default='#3b82f6'),
        sa.Column('secondary_color', sa.String(length=7), nullable=True, server_default='#1e40af'),

        # Social linkovi
        sa.Column('facebook_url', sa.String(length=300), nullable=True),
        sa.Column('instagram_url', sa.String(length=300), nullable=True),
        sa.Column('twitter_url', sa.String(length=300), nullable=True),
        sa.Column('linkedin_url', sa.String(length=300), nullable=True),
        sa.Column('youtube_url', sa.String(length=300), nullable=True),
        sa.Column('tiktok_url', sa.String(length=300), nullable=True),
        sa.Column('website_url', sa.String(length=300), nullable=True),

        # SEO
        sa.Column('meta_title', sa.String(length=100), nullable=True),
        sa.Column('meta_description', sa.String(length=200), nullable=True),
        sa.Column('meta_keywords', sa.String(length=300), nullable=True),

        # Cenovnik prikaz
        sa.Column('show_prices', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('price_disclaimer', sa.String(length=500), nullable=True,
                  server_default='Cene su okvirne i podložne promenama nakon dijagnostike.'),

        # Custom domen
        sa.Column('custom_domain', sa.String(length=255), nullable=True),
        sa.Column('custom_domain_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('custom_domain_verification_token', sa.String(length=64), nullable=True),
        sa.Column('custom_domain_verified_at', sa.DateTime(), nullable=True),
        sa.Column('custom_domain_ssl_status', sa.String(length=20), nullable=True, server_default='pending'),

        # Dodatne sekcije
        sa.Column('about_title', sa.String(length=200), nullable=True),
        sa.Column('about_content', sa.Text(), nullable=True),
        sa.Column('why_us_title', sa.String(length=200), nullable=True),
        sa.Column('why_us_items', sa.JSON(), nullable=True),
        sa.Column('gallery_images', sa.JSON(), nullable=True),
        sa.Column('testimonials', sa.JSON(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),

        # Constraints
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Kreiraj indekse
    op.create_index('ix_tenant_public_profile_tenant_id', 'tenant_public_profile', ['tenant_id'], unique=True)
    op.create_index('ix_tenant_public_profile_custom_domain', 'tenant_public_profile', ['custom_domain'], unique=True)
    op.create_index('ix_tenant_public_profile_is_public', 'tenant_public_profile', ['is_public'], unique=False)


def downgrade():
    op.drop_index('ix_tenant_public_profile_is_public', table_name='tenant_public_profile')
    op.drop_index('ix_tenant_public_profile_custom_domain', table_name='tenant_public_profile')
    op.drop_index('ix_tenant_public_profile_tenant_id', table_name='tenant_public_profile')
    op.drop_table('tenant_public_profile')
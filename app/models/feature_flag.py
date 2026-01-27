"""
Feature Flag model - per-feature, per-tenant flags za staged rollout.
"""

from datetime import datetime
from ..extensions import db


class FeatureFlag(db.Model):
    """Per-feature, per-tenant flags za staged rollout."""
    __tablename__ = 'feature_flag'

    id = db.Column(db.Integer, primary_key=True)
    feature_key = db.Column(db.String(50), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)  # NULL = global default
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('feature_key', 'tenant_id', name='uq_feature_tenant'),
    )

    def __repr__(self):
        scope = f'tenant={self.tenant_id}' if self.tenant_id else 'global'
        return f'<FeatureFlag {self.feature_key} ({scope}): {self.enabled}>'


def is_feature_enabled(feature_key: str, tenant_id: int = None) -> bool:
    """Proveri da li je feature uključen. Per-tenant override ima prioritet."""
    if tenant_id:
        override = FeatureFlag.query.filter_by(feature_key=feature_key, tenant_id=tenant_id).first()
        if override:
            return override.enabled
    # Global default
    default = FeatureFlag.query.filter_by(feature_key=feature_key, tenant_id=None).first()
    return default.enabled if default else False


# Inicijalni flagovi za seed
INITIAL_FLAGS = [
    ('credits_enabled', False),
    ('pos_enabled', False),
    ('b2c_marketplace_enabled', False),
    ('anonymous_b2b_enabled', False),
    ('location_scoping_enabled', True),
]


def seed_feature_flags():
    """Seed inicijalne feature flagove (idempotentno)."""
    for key, default in INITIAL_FLAGS:
        if not FeatureFlag.query.filter_by(feature_key=key, tenant_id=None).first():
            db.session.add(FeatureFlag(feature_key=key, enabled=default))
    db.session.commit()

"""
Admin Activity Log - pracenje akcija platform admina.

Loguje sve vazne akcije koje admin radi na platformi:
- Aktivacija/suspenzija servisa
- KYC verifikacija/odbijanje
- Promene pretplate
- Ostale admin akcije
"""

import enum
from datetime import datetime
from flask import request, g
from ..extensions import db


class AdminActionType(enum.Enum):
    """
    Tip admin akcije koja se loguje.
    """
    # Tenant status akcije
    ACTIVATE_TRIAL = 'ACTIVATE_TRIAL'           # DEMO -> TRIAL
    ACTIVATE_SUBSCRIPTION = 'ACTIVATE_SUBSCRIPTION'  # TRIAL -> ACTIVE
    SUSPEND_TENANT = 'SUSPEND_TENANT'           # ANY -> SUSPENDED
    UNSUSPEND_TENANT = 'UNSUSPEND_TENANT'       # SUSPENDED -> ACTIVE/TRIAL
    EXTEND_TRIAL = 'EXTEND_TRIAL'               # Produzenje trial perioda

    # KYC akcije
    KYC_VERIFY = 'KYC_VERIFY'                   # Verifikacija predstavnika
    KYC_REJECT = 'KYC_REJECT'                   # Odbijanje predstavnika
    KYC_REQUEST_RESUBMIT = 'KYC_REQUEST_RESUBMIT'  # Zahtev za ponovnim slanjem

    # Ostale akcije
    UPDATE_TENANT = 'UPDATE_TENANT'             # Azuriranje podataka tenanta
    DELETE_TENANT = 'DELETE_TENANT'             # Brisanje tenanta
    UPDATE_LOCATIONS = 'UPDATE_LOCATIONS'       # Promena broja lokacija
    UPDATE_SETTINGS = 'UPDATE_SETTINGS'         # Promena platform podesavanja

    # Billing akcije
    GENERATE_INVOICE = 'GENERATE_INVOICE'       # Generisanje fakture
    SEND_INVOICE = 'SEND_INVOICE'               # Slanje fakture na email
    VERIFY_PAYMENT = 'VERIFY_PAYMENT'           # Verifikacija uplate
    REJECT_PAYMENT = 'REJECT_PAYMENT'           # Odbijanje uplate
    BLOCK_TENANT = 'BLOCK_TENANT'               # Blokada zbog neplacanja
    UNBLOCK_TENANT = 'UNBLOCK_TENANT'           # Deblokada nakon placanja
    UPDATE_PRICING = 'UPDATE_PRICING'           # Promena cene paketa za servis

    # Trust score akcije
    TRUST_ACTIVATE = 'TRUST_ACTIVATE'           # Servis aktivirao "na rec"
    TRUST_EXPIRED = 'TRUST_EXPIRED'             # Isteklo 48h bez uplate
    UPDATE_TRUST_SCORE = 'UPDATE_TRUST_SCORE'   # Promena trust score-a

    # Messaging akcije
    SEND_MESSAGE = 'SEND_MESSAGE'               # Poslata poruka servisu

    # Bank Import akcije (v303)
    BANK_IMPORT = 'BANK_IMPORT'                 # Upload bankovnog izvoda
    BANK_IMPORT_PROCESS = 'BANK_IMPORT_PROCESS' # Procesiranje/auto-match
    BANK_IMPORT_DELETE = 'BANK_IMPORT_DELETE'   # Brisanje importa
    MANUAL_MATCH = 'MANUAL_MATCH'               # Rucno uparivanje transakcije
    UNMATCH = 'UNMATCH'                         # Ponistavanje uparivanja
    IGNORE_TRANSACTION = 'IGNORE_TRANSACTION'   # Ignorisanje transakcije
    UNIGNORE_TRANSACTION = 'UNIGNORE_TRANSACTION'  # Ponistavanje ignorisanja


class AdminActivityLog(db.Model):
    """
    Log akcija platform admina.

    Prati sve vazne admin akcije sa detaljima o tome ko je sta uradio,
    na kome, i kakav je bio rezultat.
    """
    __tablename__ = 'admin_activity_log'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Ko je izvrsio akciju (platform admin)
    admin_id = db.Column(
        db.Integer,
        db.ForeignKey('platform_admin.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    admin_email = db.Column(db.String(100))  # Denormalizovano

    # Tip akcije
    action_type = db.Column(
        db.Enum(AdminActionType),
        nullable=False,
        index=True
    )

    # Na kome je akcija izvrsena
    target_type = db.Column(db.String(50), nullable=False)  # 'tenant', 'representative'
    target_id = db.Column(db.Integer, nullable=False)
    target_name = db.Column(db.String(200))  # Ime tenanta/predstavnika za lakse citanje

    # Detalji akcije (JSON)
    # Npr: {"old_status": "DEMO", "new_status": "TRIAL", "reason": "...", "days": 60}
    details = db.Column(db.JSON, default=dict)

    # Status pre i posle (za status promene)
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50))

    # Kontekst zahteva
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))

    # Timestamp
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # Indeksi
    __table_args__ = (
        db.Index('ix_admin_activity_target', 'target_type', 'target_id'),
        db.Index('ix_admin_activity_admin_created', 'admin_id', 'created_at'),
    )

    def __repr__(self):
        return f'<AdminActivityLog {self.id}: {self.action_type.value} on {self.target_type}:{self.target_id}>'

    @classmethod
    def log(cls, action_type, target_type, target_id, target_name=None,
            old_status=None, new_status=None, details=None):
        """
        Kreira novi log zapis admin akcije.

        Args:
            action_type: AdminActionType enum vrednost
            target_type: Tip entiteta ('tenant', 'representative')
            target_id: ID entiteta
            target_name: Ime entiteta (opciono, za citljivost)
            old_status: Status pre akcije
            new_status: Status posle akcije
            details: Dodatni detalji (dict)

        Returns:
            Kreirani AdminActivityLog objekat
        """
        # Dohvati admina iz konteksta
        admin = None
        admin_email = None
        if hasattr(g, 'current_admin') and g.current_admin:
            admin = g.current_admin
            admin_email = admin.email

        # Dohvati IP i user agent
        ip_address = None
        user_agent = None
        try:
            if request:
                ip_address = request.remote_addr
                user_agent = request.headers.get('User-Agent', '')[:500]
        except RuntimeError:
            pass

        log_entry = cls(
            admin_id=admin.id if admin else None,
            admin_email=admin_email,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            old_status=old_status,
            new_status=new_status,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent
        )

        db.session.add(log_entry)
        # Commit ce uraditi pozivalac

        return log_entry

    def to_dict(self):
        """Pretvara log u dict za API response."""
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'admin_email': self.admin_email,
            'action_type': self.action_type.value,
            'action_label': self.action_label,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'target_name': self.target_name,
            'old_status': self.old_status,
            'new_status': self.new_status,
            'details': self.details,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    @property
    def action_label(self):
        """Ljudski citljiv naziv akcije na srpskom."""
        labels = {
            AdminActionType.ACTIVATE_TRIAL: 'Aktivirao TRIAL',
            AdminActionType.ACTIVATE_SUBSCRIPTION: 'Aktivirao pretplatu',
            AdminActionType.SUSPEND_TENANT: 'Suspendovao servis',
            AdminActionType.UNSUSPEND_TENANT: 'Ukinuo suspenziju',
            AdminActionType.EXTEND_TRIAL: 'Produzio TRIAL',
            AdminActionType.KYC_VERIFY: 'Verifikovao predstavnika',
            AdminActionType.KYC_REJECT: 'Odbio verifikaciju',
            AdminActionType.KYC_REQUEST_RESUBMIT: 'Zahtevao ponovno slanje',
            AdminActionType.UPDATE_TENANT: 'Azurirao podatke servisa',
            AdminActionType.DELETE_TENANT: 'Obrisao servis',
            AdminActionType.UPDATE_LOCATIONS: 'Promenio broj lokacija',
            AdminActionType.UPDATE_SETTINGS: 'Promenio podesavanja platforme',
            # Billing
            AdminActionType.GENERATE_INVOICE: 'Generisao fakturu',
            AdminActionType.SEND_INVOICE: 'Poslao fakturu na email',
            AdminActionType.VERIFY_PAYMENT: 'Verifikovao uplatu',
            AdminActionType.REJECT_PAYMENT: 'Odbio uplatu',
            AdminActionType.BLOCK_TENANT: 'Blokirao servis',
            AdminActionType.UNBLOCK_TENANT: 'Deblokirao servis',
            AdminActionType.UPDATE_PRICING: 'Promenio cenu paketa',
            # Trust
            AdminActionType.TRUST_ACTIVATE: 'Servis aktivirao "na rec"',
            AdminActionType.TRUST_EXPIRED: 'Istekao "na rec" period',
            AdminActionType.UPDATE_TRUST_SCORE: 'Promenio trust score',
            # Messaging
            AdminActionType.SEND_MESSAGE: 'Poslao poruku servisu',
            # Bank Import (v303)
            AdminActionType.BANK_IMPORT: 'Uvezao bankovni izvod',
            AdminActionType.BANK_IMPORT_PROCESS: 'Procesirao izvod',
            AdminActionType.BANK_IMPORT_DELETE: 'Obrisao izvod',
            AdminActionType.MANUAL_MATCH: 'Ručno upario transakciju',
            AdminActionType.UNMATCH: 'Poništio uparivanje',
            AdminActionType.IGNORE_TRANSACTION: 'Ignorisao transakciju',
            AdminActionType.UNIGNORE_TRANSACTION: 'Poništio ignorisanje',
        }
        return labels.get(self.action_type, self.action_type.value)
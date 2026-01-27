"""
Tenant Backup Service - kreiranje enkriptovanih backup-a pre brisanja servisa.

Funkcionalnosti:
- Export svih podataka tenanta u JSON format
- AES-256 enkripcija backup fajla
- Slanje enkriptovanog backup-a na email
"""

import os
import json
import base64
import hashlib
import secrets
from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, Any, Tuple, Optional

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from ..extensions import db
from ..models import Tenant, User, ServiceTicket, SubscriptionPayment
from ..models.tenant import ServiceLocation, TenantStatus
from ..models.representative import ServiceRepresentative


class TenantBackupService:
    """
    Servis za kreiranje enkriptovanih backup-a podataka tenanta.

    Koristi AES-256-GCM enkripciju za siguran backup.
    Salje backup na backup@servishub.rs pre brisanja servisa.
    """

    # SendGrid API endpoint
    SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"

    # Backup email
    BACKUP_EMAIL = "backup@servishub.rs"

    def __init__(self):
        """Inicijalizacija backup servisa."""
        self.api_key = os.environ.get('SENDGRID_API_KEY')
        self.from_email = os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@servishub.rs')
        self.from_name = os.environ.get('SENDGRID_FROM_NAME', 'ServisHub Backup')

    def _generate_encryption_key(self) -> Tuple[bytes, str]:
        """
        Generise AES-256 kljuc za enkripciju.

        Returns:
            Tuple (key_bytes, key_hex_string)
        """
        # 32 bytes = 256 bits za AES-256
        key = secrets.token_bytes(32)
        key_hex = key.hex()
        return key, key_hex

    def _encrypt_data(self, data: str, key: bytes) -> Tuple[bytes, bytes, bytes]:
        """
        Enkriptuje string podatke pomocu AES-256-GCM.

        Args:
            data: String podaci za enkripciju
            key: 32-byte AES kljuc

        Returns:
            Tuple (nonce, ciphertext, tag)
        """
        # Generisi nonce (12 bytes za GCM)
        nonce = secrets.token_bytes(12)

        # Kreiraj cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()

        # Enkriptuj
        ciphertext = encryptor.update(data.encode('utf-8')) + encryptor.finalize()
        tag = encryptor.tag

        return nonce, ciphertext, tag

    def _export_tenant_data(self, tenant_id: int) -> Dict[str, Any]:
        """
        Exportuje KOMPLETNE podatke tenanta u optimizovanom formatu.

        Uključuje sve tabele povezane sa tenantom za potpuni backup.

        Args:
            tenant_id: ID tenanta

        Returns:
            Dictionary sa svim podacima tenanta
        """
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return {}

        def dt(val):
            """Helper za kompaktnu datetime konverziju."""
            return val.isoformat() if val else None

        def fl(val):
            """Helper za float konverziju."""
            return float(val) if val else None

        # Osnovni podaci tenanta
        data = {
            '_v': 2,  # Verzija backup formata
            '_ts': datetime.now(timezone.utc).isoformat(),
            '_tid': tenant_id,
            't': {  # tenant
                'id': tenant.id,
                'slug': tenant.slug,
                'name': tenant.name,
                'pib': tenant.pib,
                'mb': tenant.maticni_broj,
                'addr': tenant.adresa_sedista,
                'city': tenant.grad,
                'zip': tenant.postanski_broj,
                'email': tenant.email,
                'phone': tenant.telefon,
                'bank': tenant.bank_account,
                'status': tenant.status.value if tenant.status else None,
                'demo_end': dt(tenant.demo_ends_at),
                'trial_end': dt(tenant.trial_ends_at),
                'sub_end': dt(tenant.subscription_ends_at),
                'settings': tenant.settings_json,
                'created': dt(tenant.created_at),
                'updated': dt(tenant.updated_at),
            }
        }

        # Lokacije
        locations = ServiceLocation.query.filter_by(tenant_id=tenant_id).all()
        data['loc'] = [{
            'id': l.id, 'name': l.name, 'addr': l.address, 'city': l.city,
            'zip': l.postal_code, 'phone': l.phone, 'email': l.email,
            'hours': l.working_hours_json,
            'lat': fl(l.latitude), 'lng': fl(l.longitude),
            'primary': l.is_primary, 'active': l.is_active, 'created': dt(l.created_at)
        } for l in locations]

        # Korisnici (bez password hash-a)
        users = User.query.filter_by(tenant_id=tenant_id).all()
        data['usr'] = [{
            'id': u.id, 'email': u.email, 'ime': u.ime, 'prezime': u.prezime,
            'phone': u.phone, 'role': u.role.value if u.role else None,
            'active': u.is_active, 'last_login': dt(u.last_login_at), 'created': dt(u.created_at)
        } for u in users]

        # User-Location veze
        try:
            from ..models.user import UserLocation
            user_ids = [u.id for u in users]
            if user_ids:
                user_locs = UserLocation.query.filter(UserLocation.user_id.in_(user_ids)).all()
                data['usr_loc'] = [{'uid': ul.user_id, 'lid': ul.location_id} for ul in user_locs]
        except:
            pass

        # KYC Predstavnici
        representatives = ServiceRepresentative.query.filter_by(tenant_id=tenant_id).all()
        data['rep'] = [{
            'id': r.id, 'ime': r.ime, 'prezime': r.prezime, 'jmbg': r.jmbg,
            'lk': r.broj_licne_karte, 'addr': r.adresa, 'phone': r.telefon, 'email': r.email,
            'lk_front': r.lk_front_url, 'lk_back': r.lk_back_url,
            'primary': r.is_primary, 'status': r.status.value if r.status else None,
            'verified': dt(r.verified_at), 'created': dt(r.created_at)
        } for r in representatives]

        # Servisni nalozi - KOMPLETNI podaci
        tickets = ServiceTicket.query.filter_by(tenant_id=tenant_id).all()
        data['tkt'] = [{
            'id': t.id, 'num': t.ticket_number,
            'cust': t.customer_name, 'cphone': t.customer_phone, 'cemail': t.customer_email,
            'brand': t.brand, 'model': t.model, 'imei': t.imei,
            'cond': t.device_condition, 'problem': t.problem_description, 'resolution': t.resolution_details,
            'status': t.status, 'priority': t.priority,
            'est_price': fl(t.estimated_price), 'final_price': fl(t.final_price), 'curr': t.currency,
            'warranty': t.warranty_days, 'closed': dt(t.closed_at),
            'collected': t.collected, 'collected_at': dt(t.collected_at),
            'loc_id': t.location_id, 'tech_id': t.technician_id, 'user_id': t.created_by_id,
            'created': dt(t.created_at)
        } for t in tickets]

        # Uplate
        payments = SubscriptionPayment.query.filter_by(tenant_id=tenant_id).all()
        data['pay'] = [{
            'id': p.id, 'inv': getattr(p, 'invoice_number', None),
            'amt': fl(p.total_amount) if hasattr(p, 'total_amount') else fl(p.amount),
            'curr': p.currency, 'status': p.status, 'method': p.payment_method,
            'start': dt(p.period_start), 'end': dt(p.period_end),
            'paid': dt(p.paid_at) if hasattr(p, 'paid_at') else None,
            'items': getattr(p, 'items_json', None),
            'created': dt(p.created_at)
        } for p in payments]

        # Inventar - Telefoni
        try:
            from ..models.inventory import PhoneListing
            phones = PhoneListing.query.filter_by(tenant_id=tenant_id).all()
            data['phones'] = [{
                'id': p.id, 'brand': p.brand, 'model': p.model, 'imei': p.imei,
                'storage': p.storage, 'color': p.color, 'cond': p.condition,
                'buy_price': fl(p.purchase_price), 'sell_price': fl(p.selling_price),
                'curr': p.currency, 'status': p.status, 'notes': p.notes,
                'sold': dt(p.sold_at), 'created': dt(p.created_at)
            } for p in phones]
        except:
            data['phones'] = []

        # Inventar - Delovi
        try:
            from ..models.inventory import SparePart
            parts = SparePart.query.filter_by(tenant_id=tenant_id).all()
            data['parts'] = [{
                'id': p.id, 'name': p.name, 'sku': p.sku, 'cat': p.category,
                'qty': p.quantity, 'min_qty': p.min_quantity,
                'buy_price': fl(p.purchase_price), 'sell_price': fl(p.selling_price),
                'curr': p.currency, 'loc_id': p.location_id,
                'created': dt(p.created_at)
            } for p in parts]
        except:
            data['parts'] = []

        # Narudzbine
        try:
            from ..models.order import Order, OrderItem
            orders = Order.query.filter_by(tenant_id=tenant_id).all()
            data['orders'] = []
            for o in orders:
                items = OrderItem.query.filter_by(order_id=o.id).all()
                data['orders'].append({
                    'id': o.id, 'num': o.order_number, 'status': o.status,
                    'total': fl(o.total_amount), 'curr': o.currency,
                    'supplier_id': o.supplier_tenant_id, 'notes': o.notes,
                    'created': dt(o.created_at),
                    'items': [{'id': i.id, 'name': i.name, 'qty': i.quantity,
                               'price': fl(i.unit_price)} for i in items]
                })
        except:
            data['orders'] = []

        # Usluge
        try:
            from ..models.service import TenantService
            services = TenantService.query.filter_by(tenant_id=tenant_id).all()
            data['svc'] = [{
                'id': s.id, 'name': s.name, 'desc': s.description,
                'price': fl(s.price), 'curr': s.currency, 'duration': s.duration_minutes,
                'active': s.is_active, 'created': dt(s.created_at)
            } for s in services]
        except:
            data['svc'] = []

        # Javni profil
        try:
            from ..models.tenant_public_profile import TenantPublicProfile
            profile = TenantPublicProfile.query.filter_by(tenant_id=tenant_id).first()
            if profile:
                data['profile'] = {
                    'id': profile.id, 'bio': profile.bio, 'logo': profile.logo_url,
                    'cover': profile.cover_url, 'website': profile.website,
                    'social': profile.social_links_json, 'visible': profile.is_visible
                }
        except:
            pass

        # Poruke (sistemske)
        try:
            from ..models.tenant_message import TenantMessage
            messages = TenantMessage.query.filter_by(tenant_id=tenant_id).all()
            data['msg'] = [{
                'id': m.id, 'type': m.message_type, 'title': m.title,
                'body': m.body, 'read': m.is_read, 'created': dt(m.created_at)
            } for m in messages]
        except:
            data['msg'] = []

        # Konekcije sa drugim servisima
        try:
            from ..models.tenant_connection import TenantConnection
            conns = TenantConnection.query.filter(
                db.or_(
                    TenantConnection.tenant_a_id == tenant_id,
                    TenantConnection.tenant_b_id == tenant_id
                )
            ).all()
            data['conn'] = [{
                'id': c.id, 'a': c.tenant_a_id, 'b': c.tenant_b_id,
                'status': c.status, 'created': dt(c.created_at)
            } for c in conns]
        except:
            data['conn'] = []

        # Statistika
        data['_stats'] = {
            'loc': len(data.get('loc', [])),
            'usr': len(data.get('usr', [])),
            'rep': len(data.get('rep', [])),
            'tkt': len(data.get('tkt', [])),
            'pay': len(data.get('pay', [])),
            'phones': len(data.get('phones', [])),
            'parts': len(data.get('parts', [])),
            'orders': len(data.get('orders', [])),
            'svc': len(data.get('svc', [])),
            'msg': len(data.get('msg', [])),
        }

        return data

    def create_encrypted_backup(self, tenant_id: int) -> Tuple[bytes, str, str]:
        """
        Kreira enkriptovani backup tenanta.

        Args:
            tenant_id: ID tenanta za backup

        Returns:
            Tuple (encrypted_data, encryption_key_hex, filename)
        """
        # Export podataka - kompaktan JSON format bez razmaka
        data = self._export_tenant_data(tenant_id)
        json_data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

        # Generisi kljuc
        key, key_hex = self._generate_encryption_key()

        # Enkriptuj
        nonce, ciphertext, tag = self._encrypt_data(json_data, key)

        # Kombinuj u jedan fajl: nonce (12) + tag (16) + ciphertext
        encrypted_data = nonce + tag + ciphertext

        # Filename
        tenant_name = data.get('tenant', {}).get('name', 'unknown')
        safe_name = "".join(c for c in tenant_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')[:50]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"backup_{safe_name}_{tenant_id}_{timestamp}.enc"

        return encrypted_data, key_hex, filename

    def send_backup_email(
        self,
        tenant_id: int,
        tenant_name: str,
        encrypted_data: bytes,
        encryption_key: str,
        filename: str,
        deleted_by_email: str
    ) -> bool:
        """
        Salje enkriptovani backup na backup email.

        Args:
            tenant_id: ID tenanta
            tenant_name: Ime tenanta
            encrypted_data: Enkriptovani podaci
            encryption_key: Hex string kljuca za dekripciju
            filename: Ime fajla
            deleted_by_email: Email admina koji je obrisao

        Returns:
            bool: True ako je uspesno poslato
        """
        if not self.api_key:
            print(f"[BACKUP] DEV MODE - Would send backup to {self.BACKUP_EMAIL}")
            print(f"[BACKUP] Filename: {filename}")
            print(f"[BACKUP] Encryption key: {encryption_key}")
            print(f"[BACKUP] Data size: {len(encrypted_data)} bytes")
            return True

        # Base64 encode za attachment
        encoded_data = base64.b64encode(encrypted_data).decode('utf-8')

        # HTML sadrzaj emaila
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="background: #dc2626; padding: 20px; color: white;">
                <h1 style="margin: 0;">ServisHub - Backup Pre Brisanja</h1>
            </div>

            <div style="padding: 20px; background: #f9fafb;">
                <h2>Servis Obrisan</h2>

                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Tenant ID:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{tenant_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Naziv servisa:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{tenant_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Obrisao:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{deleted_by_email}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Datum brisanja:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</td>
                    </tr>
                </table>

                <div style="margin-top: 20px; padding: 15px; background: #fef3c7; border: 1px solid #f59e0b; border-radius: 5px;">
                    <h3 style="margin-top: 0; color: #92400e;">Enkripcioni Kljuc</h3>
                    <p style="margin-bottom: 0;">
                        Fajl je enkriptovan pomocu AES-256-GCM.
                        Kljuc za dekripciju:
                    </p>
                    <code style="display: block; margin-top: 10px; padding: 10px; background: #fff; border: 1px solid #ddd; word-break: break-all; font-size: 12px;">
                        {encryption_key}
                    </code>
                </div>

                <p style="margin-top: 20px; color: #6b7280; font-size: 14px;">
                    Backup fajl je prilozen ovom emailu. Sacuvajte kljuc na sigurnom mestu -
                    bez njega nije moguce dekriptovati podatke.
                </p>
            </div>

            <div style="padding: 15px; background: #1f2937; color: #9ca3af; font-size: 12px; text-align: center;">
                &copy; {datetime.now().year} ServisHub. Automatski generisan backup.
            </div>
        </body>
        </html>
        """

        text_content = f"""
ServisHub - Backup Pre Brisanja

Servis Obrisan
--------------
Tenant ID: {tenant_id}
Naziv servisa: {tenant_name}
Obrisao: {deleted_by_email}
Datum brisanja: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

ENKRIPCIONI KLJUC (AES-256-GCM):
{encryption_key}

Backup fajl je prilozen ovom emailu. Sacuvajte kljuc na sigurnom mestu.

---
(c) {datetime.now().year} ServisHub
        """

        try:
            payload = {
                "personalizations": [
                    {
                        "to": [{"email": self.BACKUP_EMAIL}],
                        "subject": f"[BACKUP] Servis obrisan: {tenant_name} (ID: {tenant_id})"
                    }
                ],
                "from": {
                    "email": self.from_email,
                    "name": self.from_name
                },
                "content": [
                    {"type": "text/plain", "value": text_content},
                    {"type": "text/html", "value": html_content}
                ],
                "attachments": [
                    {
                        "content": encoded_data,
                        "filename": filename,
                        "type": "application/octet-stream",
                        "disposition": "attachment"
                    }
                ]
            }

            print(f"[BACKUP] Sending backup email to {self.BACKUP_EMAIL}")
            print(f"[BACKUP] Filename: {filename}, Size: {len(encrypted_data)} bytes")

            response = requests.post(
                self.SENDGRID_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=30
            )

            if response.status_code in [200, 201, 202]:
                print(f"[BACKUP] Email sent successfully")
                return True
            else:
                print(f"[BACKUP] Failed to send email: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"[BACKUP] Error sending email: {str(e)}")
            return False

    def backup_and_delete_tenant(
        self,
        tenant_id: int,
        admin_email: str,
        create_backup: bool = True
    ) -> Tuple[bool, str]:
        """
        Opciono kreira backup tenanta, salje na email, i brise sve podatke.

        Args:
            tenant_id: ID tenanta za brisanje
            admin_email: Email admina koji brise
            create_backup: Da li da kreira backup pre brisanja

        Returns:
            Tuple (success: bool, message: str)
        """
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return False, "Tenant nije pronadjen"

        tenant_name = tenant.name

        try:
            # 1. Opciono kreiraj i posalji backup
            if create_backup:
                print(f"[BACKUP] Creating encrypted backup for tenant {tenant_id}...")
                encrypted_data, encryption_key, filename = self.create_encrypted_backup(tenant_id)

                print(f"[BACKUP] Sending backup email...")
                email_sent = self.send_backup_email(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    encrypted_data=encrypted_data,
                    encryption_key=encryption_key,
                    filename=filename,
                    deleted_by_email=admin_email
                )

                if not email_sent:
                    return False, "Greska pri slanju backup emaila. Brisanje otkazano."
            else:
                print(f"[BACKUP] Skipping backup (user requested no backup)")

            # 2. Obrisi sve povezane podatke
            print(f"[BACKUP] Deleting tenant data...")

            # Prvo brisi child zapise koji imaju foreign key na tenant
            # Redosled je bitan zbog FK constraints

            # Message threads i poruke
            try:
                from ..models.message_thread import MessageThread, Message, ThreadParticipant
                threads = MessageThread.query.filter_by(tenant_id=tenant_id).all()
                for thread in threads:
                    Message.query.filter_by(thread_id=thread.id).delete()
                    ThreadParticipant.query.filter_by(thread_id=thread.id).delete()
                MessageThread.query.filter_by(tenant_id=tenant_id).delete()
                # Cleanup references from other tenants' threads
                if hasattr(MessageThread, 'other_tenant_id'):
                    MessageThread.query.filter_by(other_tenant_id=tenant_id).update({MessageThread.other_tenant_id: None})
                if hasattr(Message, 'sender_tenant_id'):
                    Message.query.filter_by(sender_tenant_id=tenant_id).update({Message.sender_tenant_id: None})
            except Exception as e:
                print(f"[BACKUP] Note: MessageThread cleanup: {e}")

            # Tenant connections
            try:
                from ..models.tenant_connection import TenantConnection
                TenantConnection.query.filter(
                    db.or_(
                        TenantConnection.tenant_a_id == tenant_id,
                        TenantConnection.tenant_b_id == tenant_id
                    )
                ).delete(synchronize_session='fetch')
            except Exception as e:
                print(f"[BACKUP] Note: TenantConnection cleanup: {e}")

            # Tenant messages
            try:
                from ..models.tenant_message import TenantMessage
                TenantMessage.query.filter_by(tenant_id=tenant_id).delete()
            except Exception as e:
                print(f"[BACKUP] Note: TenantMessage cleanup: {e}")

            # Tenant public profile
            try:
                from ..models.tenant_public_profile import TenantPublicProfile
                TenantPublicProfile.query.filter_by(tenant_id=tenant_id).delete()
            except Exception as e:
                print(f"[BACKUP] Note: TenantPublicProfile cleanup: {e}")

            # Package change history
            try:
                from ..models.package_change_history import PackageChangeHistory
                PackageChangeHistory.query.filter_by(tenant_id=tenant_id).delete()
            except Exception as e:
                print(f"[BACKUP] Note: PackageChangeHistory cleanup: {e}")

            # Inventory
            try:
                from ..models.inventory import PhoneListing, SparePart
                PhoneListing.query.filter_by(tenant_id=tenant_id).delete()
                SparePart.query.filter_by(tenant_id=tenant_id).delete()
            except Exception as e:
                print(f"[BACKUP] Note: Inventory cleanup: {e}")

            # Orders
            try:
                from ..models.order import Order, OrderItem
                orders = Order.query.filter_by(tenant_id=tenant_id).all()
                for order in orders:
                    OrderItem.query.filter_by(order_id=order.id).delete()
                Order.query.filter_by(tenant_id=tenant_id).delete()
                Order.query.filter_by(supplier_tenant_id=tenant_id).update({Order.supplier_tenant_id: None})
            except Exception as e:
                print(f"[BACKUP] Note: Order cleanup: {e}")

            # Services
            try:
                from ..models.service import TenantService
                TenantService.query.filter_by(tenant_id=tenant_id).delete()
            except Exception as e:
                print(f"[BACKUP] Note: TenantService cleanup: {e}")

            # Servisni nalozi
            from ..models.ticket import TicketNotificationLog
            for ticket in ServiceTicket.query.filter_by(tenant_id=tenant_id).all():
                # Obrisi notification logs za ticket
                TicketNotificationLog.query.filter_by(ticket_id=ticket.id).delete()
            ServiceTicket.query.filter_by(tenant_id=tenant_id).delete()

            # KYC predstavnici
            ServiceRepresentative.query.filter_by(tenant_id=tenant_id).delete()

            # Bank transactions - unmatch sve uparene transakcije za ovaj tenant
            try:
                from ..models.bank_import import BankTransaction
                # Nadji sve uplate ovog tenanta
                tenant_payment_ids = [p.id for p in SubscriptionPayment.query.filter_by(tenant_id=tenant_id).all()]
                if tenant_payment_ids:
                    # Unmatch transakcije koje su uparene sa ovim uplatama
                    BankTransaction.query.filter(
                        BankTransaction.matched_payment_id.in_(tenant_payment_ids)
                    ).update({
                        BankTransaction.matched_payment_id: None,
                        BankTransaction.status: 'PENDING',
                        BankTransaction.matched_by: None,
                        BankTransaction.matched_at: None
                    }, synchronize_session='fetch')
            except Exception as e:
                print(f"[BACKUP] Note: BankTransaction cleanup: {e}")

            # Subscription Payments - brisemo jer vise nema tenanta
            SubscriptionPayment.query.filter_by(tenant_id=tenant_id).delete()

            # Korisnici - prvo brisi user_location veze
            from ..models.user import UserLocation
            users = User.query.filter_by(tenant_id=tenant_id).all()
            for user in users:
                UserLocation.query.filter_by(user_id=user.id).delete()
            User.query.filter_by(tenant_id=tenant_id).delete()

            # Lokacije
            ServiceLocation.query.filter_by(tenant_id=tenant_id).delete()

            # Audit log - SET NULL umesto delete (za istoriju)
            from ..models.audit import AuditLog
            AuditLog.query.filter_by(tenant_id=tenant_id).update({AuditLog.tenant_id: None})

            # Konacno obrisi tenanta
            db.session.delete(tenant)
            db.session.commit()

            print(f"[BACKUP] Tenant {tenant_id} ({tenant_name}) successfully deleted")

            if create_backup:
                return True, f"Servis '{tenant_name}' uspesno obrisan. Backup poslat na {self.BACKUP_EMAIL}."
            else:
                return True, f"Servis '{tenant_name}' uspesno obrisan (bez backup-a)."

        except Exception as e:
            db.session.rollback()
            print(f"[BACKUP] Error during backup/delete: {str(e)}")
            return False, f"Greska prilikom brisanja: {str(e)}"


# Singleton instanca
tenant_backup_service = TenantBackupService()

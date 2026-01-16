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
        Exportuje sve podatke tenanta u dictionary.

        Args:
            tenant_id: ID tenanta

        Returns:
            Dictionary sa svim podacima tenanta
        """
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return {}

        # Osnovni podaci tenanta
        data = {
            'export_timestamp': datetime.now(timezone.utc).isoformat(),
            'tenant': {
                'id': tenant.id,
                'slug': tenant.slug,
                'name': tenant.name,
                'pib': tenant.pib,
                'maticni_broj': tenant.maticni_broj,
                'adresa_sedista': tenant.adresa_sedista,
                'grad': tenant.grad,
                'postanski_broj': tenant.postanski_broj,
                'email': tenant.email,
                'telefon': tenant.telefon,
                'bank_account': tenant.bank_account,
                'status': tenant.status.value if tenant.status else None,
                'demo_ends_at': tenant.demo_ends_at.isoformat() if tenant.demo_ends_at else None,
                'trial_ends_at': tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
                'subscription_ends_at': tenant.subscription_ends_at.isoformat() if tenant.subscription_ends_at else None,
                'settings_json': tenant.settings_json,
                'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
                'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
            }
        }

        # Lokacije
        locations = ServiceLocation.query.filter_by(tenant_id=tenant_id).all()
        data['locations'] = [{
            'id': loc.id,
            'name': loc.name,
            'address': loc.address,
            'city': loc.city,
            'postal_code': loc.postal_code,
            'phone': loc.phone,
            'email': loc.email,
            'working_hours_json': loc.working_hours_json,
            'latitude': float(loc.latitude) if loc.latitude else None,
            'longitude': float(loc.longitude) if loc.longitude else None,
            'is_primary': loc.is_primary,
            'is_active': loc.is_active,
            'created_at': loc.created_at.isoformat() if loc.created_at else None,
        } for loc in locations]

        # Korisnici
        users = User.query.filter_by(tenant_id=tenant_id).all()
        data['users'] = [{
            'id': user.id,
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
            'phone': user.phone,
            'role': user.role.value if user.role else None,
            'is_active': user.is_active,
            'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            # NE exportujemo password_hash iz sigurnosnih razloga
        } for user in users]

        # Predstavnici (KYC)
        representatives = ServiceRepresentative.query.filter_by(tenant_id=tenant_id).all()
        data['representatives'] = [{
            'id': rep.id,
            'ime': rep.ime,
            'prezime': rep.prezime,
            'jmbg': rep.jmbg,  # Enkriptovano u backup-u
            'broj_licne_karte': rep.broj_licne_karte,
            'adresa': rep.adresa,
            'telefon': rep.telefon,
            'email': rep.email,
            'lk_front_url': rep.lk_front_url,
            'lk_back_url': rep.lk_back_url,
            'is_primary': rep.is_primary,
            'status': rep.status.value if rep.status else None,
            'verified_at': rep.verified_at.isoformat() if rep.verified_at else None,
            'created_at': rep.created_at.isoformat() if rep.created_at else None,
        } for rep in representatives]

        # Servisni nalozi
        tickets = ServiceTicket.query.filter_by(tenant_id=tenant_id).all()
        data['service_tickets'] = [{
            'id': ticket.id,
            'ticket_number': ticket.ticket_number,
            'customer_name': ticket.customer_name,
            'customer_phone': ticket.customer_phone,
            'customer_email': ticket.customer_email,
            'brand': ticket.brand,
            'model': ticket.model,
            'imei': ticket.imei,
            'device_condition': ticket.device_condition,
            'problem_description': ticket.problem_description,
            'resolution_details': ticket.resolution_details,
            'status': ticket.status,
            'priority': ticket.priority,
            'estimated_price': float(ticket.estimated_price) if ticket.estimated_price else None,
            'final_price': float(ticket.final_price) if ticket.final_price else None,
            'currency': ticket.currency,
            'warranty_days': ticket.warranty_days,
            'closed_at': ticket.closed_at.isoformat() if ticket.closed_at else None,
            'collected': ticket.collected,
            'collected_at': ticket.collected_at.isoformat() if ticket.collected_at else None,
            'created_at': ticket.created_at.isoformat() if ticket.created_at else None,
        } for ticket in tickets]

        # Uplate
        payments = SubscriptionPayment.query.filter_by(tenant_id=tenant_id).all()
        data['payments'] = [{
            'id': pay.id,
            'amount': float(pay.amount) if pay.amount else None,
            'currency': pay.currency,
            'status': pay.status,
            'payment_method': pay.payment_method,
            'period_start': pay.period_start.isoformat() if pay.period_start else None,
            'period_end': pay.period_end.isoformat() if pay.period_end else None,
            'created_at': pay.created_at.isoformat() if pay.created_at else None,
        } for pay in payments]

        # Dodaj statistiku
        data['statistics'] = {
            'total_locations': len(data['locations']),
            'total_users': len(data['users']),
            'total_representatives': len(data['representatives']),
            'total_tickets': len(data['service_tickets']),
            'total_payments': len(data['payments']),
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
        # Export podataka
        data = self._export_tenant_data(tenant_id)
        json_data = json.dumps(data, ensure_ascii=False, indent=2)

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

            # Servisni nalozi
            from ..models.ticket import TicketNotificationLog
            for ticket in ServiceTicket.query.filter_by(tenant_id=tenant_id).all():
                # Obrisi notification logs za ticket
                TicketNotificationLog.query.filter_by(ticket_id=ticket.id).delete()
            ServiceTicket.query.filter_by(tenant_id=tenant_id).delete()

            # KYC predstavnici
            ServiceRepresentative.query.filter_by(tenant_id=tenant_id).delete()

            # Uplate (opciono - mozemo zadrzati za finansijsku evidenciju)
            # SubscriptionPayment.query.filter_by(tenant_id=tenant_id).delete()

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

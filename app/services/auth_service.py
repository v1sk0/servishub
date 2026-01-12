"""
Auth Service - poslovna logika za autentifikaciju.

Ovaj servis sadrzi logiku za registraciju, login, refresh tokena
i sve operacije vezane za autentifikaciju korisnika i admina.
"""

from datetime import datetime
from typing import Tuple, Optional
from flask import current_app

from ..extensions import db
from ..models import (
    Tenant, ServiceLocation, TenantStatus,
    TenantUser, UserRole,
    PlatformAdmin,
    AuditLog, AuditAction
)
from ..api.middleware.jwt_utils import (
    create_access_token, create_refresh_token,
    create_admin_access_token, create_admin_refresh_token,
    decode_token, TokenType
)


class AuthError(Exception):
    """Bazna klasa za auth greske."""
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(message)


class AuthService:
    """
    Servis za autentifikaciju korisnika i admina.

    Sadrzi metode za:
    - Registraciju novog servisa (tenant + owner)
    - Login korisnika
    - Refresh tokena
    - Login platform admina
    """

    def register_tenant(
        self,
        company_name: str,
        company_email: str,
        company_phone: Optional[str],
        pib: Optional[str],
        location_name: str,
        location_address: Optional[str],
        location_city: str,
        owner_email: str,
        owner_password: str,
        owner_ime: str,
        owner_prezime: str,
        owner_phone: Optional[str] = None
    ) -> Tuple[Tenant, TenantUser]:
        """
        Registruje novi servis (tenant) sa prvom lokacijom i vlasnikom.

        Kreira:
        1. Tenant (preduzece) u PENDING statusu
        2. ServiceLocation (prva lokacija, is_primary=True)
        3. TenantUser (vlasnik, role=OWNER)

        Servis ostaje u PENDING statusu dok platform admin ne odobri
        i aktivira trial period.

        Args:
            company_name: Naziv preduzeca
            company_email: Email preduzeca
            company_phone: Telefon preduzeca (opciono)
            pib: PIB preduzeca (opciono)
            location_name: Naziv prve lokacije
            location_address: Adresa lokacije (opciono)
            location_city: Grad lokacije
            owner_email: Email vlasnika za login
            owner_password: Lozinka vlasnika
            owner_ime: Ime vlasnika
            owner_prezime: Prezime vlasnika
            owner_phone: Telefon vlasnika (opciono)

        Returns:
            Tuple (Tenant, TenantUser) - kreirani tenant i owner

        Raises:
            AuthError: Ako email vec postoji ili validacija ne prodje
        """
        # Proveri da email nije vec registrovan
        existing_tenant = Tenant.query.filter_by(email=company_email).first()
        if existing_tenant:
            raise AuthError('Preduzece sa ovim email-om vec postoji', 409)

        # Proveri da owner email nije vec registrovan (globalno)
        existing_user = TenantUser.query.filter_by(email=owner_email).first()
        if existing_user:
            raise AuthError('Korisnik sa ovim email-om vec postoji', 409)

        # Proveri PIB ako je proslednjen
        if pib:
            existing_pib = Tenant.query.filter_by(pib=pib).first()
            if existing_pib:
                raise AuthError('Preduzece sa ovim PIB-om vec postoji', 409)

        try:
            # Kreiraj tenant
            tenant = Tenant(
                name=company_name,
                email=company_email,
                telefon=company_phone,
                pib=pib,
                status=TenantStatus.PENDING,
                settings_json={
                    'warranty_defaults': {
                        'default': current_app.config.get('DEFAULT_WARRANTY_DAYS', 45)
                    },
                    'currency': 'RSD'
                }
            )
            db.session.add(tenant)
            db.session.flush()  # Da dobijemo tenant.id

            # Kreiraj prvu lokaciju
            location = ServiceLocation(
                tenant_id=tenant.id,
                name=location_name,
                address=location_address,
                city=location_city,
                is_primary=True,
                is_active=True
            )
            db.session.add(location)
            db.session.flush()

            # Kreiraj owner korisnika
            owner = TenantUser(
                tenant_id=tenant.id,
                email=owner_email,
                ime=owner_ime,
                prezime=owner_prezime,
                phone=owner_phone,
                role=UserRole.OWNER,
                is_active=True
            )
            owner.set_password(owner_password)
            db.session.add(owner)

            # Commit sve
            db.session.commit()

            # Loguj registraciju
            AuditLog.log(
                entity_type='tenant',
                entity_id=tenant.id,
                action=AuditAction.CREATE,
                changes={'registered': {'company': company_name, 'owner': owner_email}},
                tenant_id=tenant.id
            )
            db.session.commit()

            return tenant, owner

        except Exception as e:
            db.session.rollback()
            raise AuthError(f'Greska pri registraciji: {str(e)}', 500)

    def login(self, email: str, password: str) -> Tuple[TenantUser, Tenant, dict]:
        """
        Autentifikuje korisnika i vraca tokene.

        Args:
            email: Email za login
            password: Lozinka

        Returns:
            Tuple (user, tenant, tokens) gde je tokens dict sa:
            - access_token
            - refresh_token
            - expires_in

        Raises:
            AuthError: Ako kredencijali nisu ispravni
        """
        # Pronadji korisnika po email-u
        user = TenantUser.query.filter_by(email=email).first()

        if not user:
            # Loguj neuspesan pokusaj
            AuditLog.log(
                entity_type='auth',
                entity_id=0,
                action=AuditAction.LOGIN_FAILED,
                changes={'email': email, 'reason': 'user_not_found'}
            )
            db.session.commit()
            raise AuthError('Pogresan email ili lozinka', 401)

        if not user.check_password(password):
            AuditLog.log(
                entity_type='auth',
                entity_id=user.id,
                action=AuditAction.LOGIN_FAILED,
                changes={'email': email, 'reason': 'wrong_password'},
                tenant_id=user.tenant_id
            )
            db.session.commit()
            raise AuthError('Pogresan email ili lozinka', 401)

        if not user.is_active:
            raise AuthError('Korisnicki nalog nije aktivan', 403)

        # Dohvati tenant
        tenant = Tenant.query.get(user.tenant_id)
        if not tenant:
            raise AuthError('Preduzece nije pronadjeno', 403)

        # Proveri status tenanta - dozvoli login za PENDING, TRIAL, ACTIVE
        # EXPIRED i SUSPENDED ne mogu da se uloguju
        if tenant.status == TenantStatus.SUSPENDED:
            raise AuthError('Vas nalog je suspendovan. Kontaktirajte podrsku.', 403)

        if tenant.status == TenantStatus.CANCELLED:
            raise AuthError('Vas nalog je otkazan.', 403)

        # Kreiraj tokene
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=tenant.id,
            role=user.role.value
        )
        refresh_token = create_refresh_token(
            user_id=user.id,
            tenant_id=tenant.id
        )

        # Azuriraj last login
        user.update_last_login()

        # Loguj uspesno logovanje
        AuditLog.log(
            entity_type='auth',
            entity_id=user.id,
            action=AuditAction.LOGIN,
            changes={'email': email},
            tenant_id=tenant.id
        )
        db.session.commit()

        tokens = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds())
        }

        return user, tenant, tokens

    def refresh_tokens(self, refresh_token: str) -> dict:
        """
        Kreira nove tokene na osnovu refresh tokena.

        Args:
            refresh_token: Validan refresh token

        Returns:
            Dict sa novim tokenima

        Raises:
            AuthError: Ako refresh token nije validan
        """
        # Dekodiraj refresh token
        payload, error = decode_token(refresh_token)

        if error:
            raise AuthError(error, 401)

        if payload.get('type') != TokenType.REFRESH:
            raise AuthError('Ocekivan je refresh token', 401)

        # Proveri da li je admin ili tenant token
        is_admin = payload.get('is_admin', False)

        if is_admin:
            # Admin refresh
            admin_id = payload.get('sub')
            admin = PlatformAdmin.query.get(admin_id)

            if not admin or not admin.is_active:
                raise AuthError('Admin nalog nije aktivan', 403)

            access_token = create_admin_access_token(admin.id, admin.role.value)
            new_refresh_token = create_admin_refresh_token(admin.id)

        else:
            # Tenant user refresh
            user_id = payload.get('sub')
            tenant_id = payload.get('tenant_id')

            user = TenantUser.query.get(user_id)
            if not user or not user.is_active:
                raise AuthError('Korisnicki nalog nije aktivan', 403)

            tenant = Tenant.query.get(tenant_id)
            if not tenant or tenant.status in (TenantStatus.SUSPENDED, TenantStatus.CANCELLED):
                raise AuthError('Preduzece nije aktivno', 403)

            access_token = create_access_token(user.id, tenant.id, user.role.value)
            new_refresh_token = create_refresh_token(user.id, tenant.id)

        return {
            'access_token': access_token,
            'refresh_token': new_refresh_token,
            'expires_in': int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds())
        }

    def admin_login(self, email: str, password: str) -> Tuple[PlatformAdmin, dict]:
        """
        Autentifikuje platform admina.

        Args:
            email: Admin email
            password: Admin lozinka

        Returns:
            Tuple (admin, tokens)

        Raises:
            AuthError: Ako kredencijali nisu ispravni
        """
        admin = PlatformAdmin.query.filter_by(email=email).first()

        if not admin:
            AuditLog.log(
                entity_type='admin_auth',
                entity_id=0,
                action=AuditAction.LOGIN_FAILED,
                changes={'email': email, 'reason': 'admin_not_found'}
            )
            db.session.commit()
            raise AuthError('Pogresan email ili lozinka', 401)

        if not admin.check_password(password):
            AuditLog.log(
                entity_type='admin_auth',
                entity_id=admin.id,
                action=AuditAction.LOGIN_FAILED,
                changes={'email': email, 'reason': 'wrong_password'}
            )
            db.session.commit()
            raise AuthError('Pogresan email ili lozinka', 401)

        if not admin.is_active:
            raise AuthError('Admin nalog nije aktivan', 403)

        # Kreiraj tokene
        access_token = create_admin_access_token(admin.id, admin.role.value)
        refresh_token = create_admin_refresh_token(admin.id)

        # Azuriraj last login
        admin.update_last_login()

        # Loguj
        AuditLog.log(
            entity_type='admin_auth',
            entity_id=admin.id,
            action=AuditAction.LOGIN,
            changes={'email': email}
        )
        db.session.commit()

        tokens = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds())
        }

        return admin, tokens

    def change_password(self, user: TenantUser, current_password: str, new_password: str):
        """
        Menja lozinku korisnika.

        Args:
            user: TenantUser objekat
            current_password: Trenutna lozinka
            new_password: Nova lozinka

        Raises:
            AuthError: Ako trenutna lozinka nije ispravna
        """
        if not user.check_password(current_password):
            raise AuthError('Trenutna lozinka nije ispravna', 400)

        user.set_password(new_password)

        AuditLog.log(
            entity_type='user',
            entity_id=user.id,
            action=AuditAction.UPDATE,
            changes={'password': {'old': '[REDACTED]', 'new': '[REDACTED]'}},
            tenant_id=user.tenant_id
        )
        db.session.commit()


# Singleton instanca servisa
auth_service = AuthService()

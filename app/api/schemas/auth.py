"""
Auth schemas - Pydantic modeli za validaciju auth podataka.

Ovi modeli se koriste za validaciju ulaznih podataka na auth
endpointima (register, login, itd.) i za formatiranje odgovora.
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


# =============================================================================
# REQUEST SCHEMAS (ulazni podaci)
# =============================================================================

class RegisterRequest(BaseModel):
    """
    Schema za registraciju novog servisa.

    Kreira:
    - Tenant (preduzece) u DEMO statusu (7 dana)
    - ServiceLocation (prva lokacija)
    - TenantUser (vlasnik, role=OWNER)
    - ServiceRepresentative (KYC podaci)
    """
    # Podaci preduzeca (Korak 1)
    company_name: str = Field(..., min_length=2, max_length=200, description="Naziv preduzeca")
    pib: Optional[str] = Field(None, max_length=9, description="PIB (9 cifara) - opciono")
    maticni_broj: Optional[str] = Field(None, max_length=8, description="Maticni broj (8 cifara)")
    adresa_sedista: str = Field(..., max_length=300, description="Adresa sedista")
    company_city: str = Field(..., min_length=2, max_length=100, description="Grad firme")
    company_postal_code: str = Field(..., min_length=4, max_length=10, description="Postanski broj firme")
    company_email: EmailStr = Field(..., description="Email preduzeca")
    company_phone: str = Field(..., max_length=30, description="Telefon preduzeca")
    bank_account: Optional[str] = Field(None, max_length=50, description="Bankovni racun (BBB-XXXXXXXXXXXXX-KK)")

    # Podaci lokacije (Korak 2)
    location_name: str = Field(..., min_length=2, max_length=100, description="Naziv lokacije")
    location_address: str = Field(..., max_length=300, description="Adresa lokacije")
    location_city: str = Field(..., min_length=2, max_length=100, description="Grad")
    location_postal_code: Optional[str] = Field(None, max_length=10, description="Postanski broj")
    location_phone: Optional[str] = Field(None, max_length=30, description="Telefon lokacije")
    location_latitude: Optional[float] = Field(None, description="Geografska sirina lokacije")
    location_longitude: Optional[float] = Field(None, description="Geografska duzina lokacije")

    # Koordinate firme (sedista)
    company_latitude: Optional[float] = Field(None, description="Geografska sirina sedista")
    company_longitude: Optional[float] = Field(None, description="Geografska duzina sedista")

    # Podaci vlasnika (Korak 3)
    owner_email: EmailStr = Field(..., description="Email vlasnika za login")
    owner_password: Optional[str] = Field(None, max_length=100, description="Lozinka (opciono za OAuth)")
    owner_ime: str = Field(..., min_length=2, max_length=50, description="Ime vlasnika")
    owner_prezime: Optional[str] = Field(None, max_length=50, description="Prezime vlasnika (opciono)")
    owner_phone: str = Field(..., max_length=30, description="Mobilni telefon vlasnika")

    # KYC podaci (Korak 4) - OPCIONI, potrebni samo za B2C marketplace
    kyc_jmbg: Optional[str] = Field(None, max_length=13, description="JMBG (13 cifara) - opciono")
    kyc_broj_licne: Optional[str] = Field(None, max_length=20, description="Broj licne karte - opciono")
    kyc_lk_front_url: Optional[str] = Field(None, description="URL slike prednje strane LK")
    kyc_lk_back_url: Optional[str] = Field(None, description="URL slike zadnje strane LK")

    # OAuth flag
    google_id: Optional[str] = Field(None, description="Google OAuth ID ako je OAuth registracija")
    phone_verified: bool = Field(False, description="Da li je telefon verifikovan SMS-om")

    @field_validator('owner_password', mode='before')
    @classmethod
    def validate_password(cls, v, info):
        """Lozinka mora imati bar jedno slovo i jedan broj (osim za OAuth)."""
        # Ako je OAuth registracija ili prazna lozinka, vrati None
        if v is None or v == '':
            return None
        # Proveri minimalnu duzinu
        if len(v) < 8:
            raise ValueError('Lozinka mora imati najmanje 8 karaktera')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Lozinka mora sadrzati bar jedno slovo')
        if not re.search(r'\d', v):
            raise ValueError('Lozinka mora sadrzati bar jedan broj')
        return v

    @field_validator('pib')
    @classmethod
    def validate_pib(cls, v):
        """PIB mora biti 9 cifara (srpski format) ako je unet."""
        if v is not None and v.strip():
            v = v.strip()
            if not re.match(r'^\d{9}$', v):
                raise ValueError('PIB mora imati tacno 9 cifara')
            return v
        return None

    @field_validator('maticni_broj')
    @classmethod
    def validate_maticni(cls, v):
        """Maticni broj mora biti 8 cifara."""
        if v is not None:
            v = v.strip()
            if v and not re.match(r'^\d{8}$', v):
                raise ValueError('Maticni broj mora imati tacno 8 cifara')
        return v

    @field_validator('kyc_jmbg')
    @classmethod
    def validate_jmbg(cls, v):
        """JMBG mora biti 13 cifara (ako je unet)."""
        if v is not None and v.strip():
            v = v.strip()
            if not re.match(r'^\d{13}$', v):
                raise ValueError('JMBG mora imati tacno 13 cifara')
            return v
        return None

    @field_validator('bank_account')
    @classmethod
    def validate_bank_account(cls, v):
        """Bankovni racun mora biti u formatu BBB-XXXXXXXXXXXXX-KK (3-13-2 = 18 cifara)."""
        if v is not None and v.strip():
            v = v.strip()
            # Serbian bank account format: 3 digits (bank code) - 13 digits (account) - 2 digits (control)
            if not re.match(r'^\d{3}-\d{13}-\d{2}$', v):
                raise ValueError('Bankovni racun mora biti u formatu BBB-XXXXXXXXXXXXX-KK (18 cifara)')
        return v if v and v.strip() else None


class LoginRequest(BaseModel):
    """Schema za login korisnika."""
    email: EmailStr = Field(..., description="Email za login")
    password: str = Field(..., min_length=1, description="Lozinka")


class TenantLoginRequest(BaseModel):
    """Schema za login korisnika unutar specifičnog tenanta."""
    tenant_secret: str = Field(..., min_length=10, description="Tajni kod tenanta iz URL-a")
    identifier: str = Field(..., min_length=1, description="Username ili email korisnika")
    password: str = Field(..., min_length=1, description="Lozinka")


class RefreshTokenRequest(BaseModel):
    """Schema za refresh tokena."""
    refresh_token: str = Field(..., description="Refresh token")


class ChangePasswordRequest(BaseModel):
    """Schema za promenu lozinke."""
    current_password: str = Field(..., description="Trenutna lozinka")
    new_password: str = Field(..., min_length=8, max_length=100, description="Nova lozinka")

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v):
        """Nova lozinka mora imati bar jedno slovo i jedan broj."""
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Lozinka mora sadrzati bar jedno slovo')
        if not re.search(r'\d', v):
            raise ValueError('Lozinka mora sadrzati bar jedan broj')
        return v


# =============================================================================
# RESPONSE SCHEMAS (izlazni podaci)
# =============================================================================

class TokenResponse(BaseModel):
    """Schema za odgovor sa tokenima."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # Sekunde do isteka access tokena


class UserResponse(BaseModel):
    """Schema za prikaz podataka korisnika."""
    id: int
    email: str
    ime: str
    prezime: str
    full_name: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class TenantResponse(BaseModel):
    """Schema za prikaz podataka tenanta."""
    id: int
    slug: str
    name: str
    email: str
    status: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Schema za odgovor na uspesni login."""
    user: UserResponse
    tenant: TenantResponse
    tokens: TokenResponse


class RegisterResponse(BaseModel):
    """Schema za odgovor na uspesnu registraciju."""
    message: str
    tenant: TenantResponse
    user: UserResponse


class MeResponse(BaseModel):
    """Schema za /auth/me endpoint."""
    user: UserResponse
    tenant: TenantResponse
    locations: list  # Lista lokacija kojima korisnik ima pristup


# =============================================================================
# ADMIN SCHEMAS
# =============================================================================

class AdminLoginRequest(BaseModel):
    """Schema za login platform admina."""
    email: EmailStr = Field(..., description="Admin email")
    password: str = Field(..., description="Admin lozinka")


class AdminLoginResponse(BaseModel):
    """Schema za odgovor na admin login."""
    admin: dict
    tokens: TokenResponse

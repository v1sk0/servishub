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

    Kreira tenant (preduzece), prvu lokaciju i owner korisnika.
    """
    # Podaci preduzeca
    company_name: str = Field(..., min_length=2, max_length=200, description="Naziv preduzeca")
    pib: Optional[str] = Field(None, max_length=20, description="PIB (opciono)")
    company_email: EmailStr = Field(..., description="Email preduzeca")
    company_phone: Optional[str] = Field(None, max_length=30, description="Telefon preduzeca")

    # Podaci lokacije
    location_name: str = Field(..., min_length=2, max_length=100, description="Naziv lokacije")
    location_address: Optional[str] = Field(None, max_length=300, description="Adresa lokacije")
    location_city: str = Field(..., min_length=2, max_length=100, description="Grad")

    # Podaci vlasnika (owner user)
    owner_email: EmailStr = Field(..., description="Email vlasnika za login")
    owner_password: str = Field(..., min_length=8, max_length=100, description="Lozinka")
    owner_ime: str = Field(..., min_length=2, max_length=50, description="Ime vlasnika")
    owner_prezime: str = Field(..., min_length=2, max_length=50, description="Prezime vlasnika")
    owner_phone: Optional[str] = Field(None, max_length=30, description="Telefon vlasnika")

    @field_validator('owner_password')
    @classmethod
    def validate_password(cls, v):
        """Lozinka mora imati bar jedno slovo i jedan broj."""
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Lozinka mora sadrzati bar jedno slovo')
        if not re.search(r'\d', v):
            raise ValueError('Lozinka mora sadrzati bar jedan broj')
        return v

    @field_validator('pib')
    @classmethod
    def validate_pib(cls, v):
        """PIB mora biti 9 cifara (srpski format)."""
        if v is not None:
            v = v.strip()
            if v and not re.match(r'^\d{9}$', v):
                raise ValueError('PIB mora imati tacno 9 cifara')
        return v


class LoginRequest(BaseModel):
    """Schema za login korisnika."""
    email: EmailStr = Field(..., description="Email za login")
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

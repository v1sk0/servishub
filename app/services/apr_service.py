"""
APR Servis - preuzimanje podataka o firmama iz Agencije za privredne registre.

Koristi APR API za dobijanje podataka o firmi na osnovu PIB-a.
Podaci koji se preuzimaju:
- Naziv firme
- Adresa sedišta
- Matični broj
- Grad/Mesto
- Poštanski broj

Dokumentacija: https://data.apr.gov.rs/
"""

import os
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class CompanyData:
    """Podaci o firmi preuzeti iz APR-a."""
    naziv: str
    pib: str
    maticni_broj: Optional[str] = None
    adresa: Optional[str] = None
    mesto: Optional[str] = None
    postanski_broj: Optional[str] = None
    email: Optional[str] = None
    delatnost: Optional[str] = None
    status: Optional[str] = None  # AKTIVAN, BRISAN, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            'naziv': self.naziv,
            'pib': self.pib,
            'maticni_broj': self.maticni_broj,
            'adresa': self.adresa,
            'mesto': self.mesto,
            'postanski_broj': self.postanski_broj,
            'email': self.email,
            'delatnost': self.delatnost,
            'status': self.status
        }


class APRService:
    """
    Servis za preuzimanje podataka o firmama iz APR-a.

    Koristi javno dostupne APR API endpointe.
    """

    # APR API endpointi
    # Novi APR API endpoint za pretragu
    APR_SEARCH_URL = "https://pretraga2.apr.gov.rs/ObssPublicDataService/api/Search"
    APR_DETAILS_URL = "https://pretraga2.apr.gov.rs/ObssPublicDataService/api/Details"

    # Alternativni endpoint - NBS registar
    NBS_URL = "https://webservices.nbs.rs/CommunicationOfficeService1_0/CommunicationOfficeService1_0.asmx"

    # Timeout za API pozive
    TIMEOUT = 10

    def __init__(self):
        """Inicijalizacija APR servisa."""
        pass

    def get_company_by_pib(self, pib: str) -> Optional[CompanyData]:
        """
        Preuzima podatke o firmi na osnovu PIB-a.

        Args:
            pib: Poreski identifikacioni broj (9 cifara)

        Returns:
            CompanyData objekat ili None ako firma nije pronađena
        """
        # Validiraj PIB format
        pib = pib.strip()
        if not pib.isdigit() or len(pib) != 9:
            print(f"[APR] Invalid PIB format: {pib}")
            return None

        # Probaj APR API
        result = self._fetch_from_apr(pib)
        if result:
            return result

        # Fallback: probaj alternativni izvor
        result = self._fetch_from_alternative(pib)
        if result:
            return result

        print(f"[APR] Company not found for PIB: {pib}")
        return None

    def _fetch_from_apr(self, pib: str) -> Optional[CompanyData]:
        """
        Preuzima podatke direktno iz APR API-ja.
        """
        try:
            # APR search endpoint
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'ServisHub/1.0'
            }

            # Pretraga po PIB-u
            search_payload = {
                "SearchType": "pib",
                "SearchValue": pib,
                "PageNumber": 1,
                "PageSize": 10
            }

            print(f"[APR] Searching for PIB: {pib}")

            response = requests.post(
                self.APR_SEARCH_URL,
                json=search_payload,
                headers=headers,
                timeout=self.TIMEOUT
            )

            print(f"[APR] Response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"[APR] Response data: {data}")

                # Parsiraj rezultate
                if data and isinstance(data, list) and len(data) > 0:
                    company = data[0]
                    return self._parse_apr_response(company, pib)
                elif data and isinstance(data, dict):
                    # Neki API vraćaju dict sa 'items' ili 'results'
                    items = data.get('items') or data.get('results') or data.get('data') or []
                    if items and len(items) > 0:
                        return self._parse_apr_response(items[0], pib)

            return None

        except requests.RequestException as e:
            print(f"[APR] Request error: {str(e)}")
            return None
        except Exception as e:
            print(f"[APR] Error: {str(e)}")
            return None

    def _fetch_from_alternative(self, pib: str) -> Optional[CompanyData]:
        """
        Alternativni izvor podataka - koristi javno dostupne API-je.

        Probamo moj-eracun.rs API koji ima javne podatke o firmama.
        """
        try:
            # moj-eracun.rs public API
            url = f"https://www.moj-eracun.rs/apis/public/v1/company/{pib}"

            headers = {
                'Accept': 'application/json',
                'User-Agent': 'ServisHub/1.0'
            }

            print(f"[APR-ALT] Trying alternative source for PIB: {pib}")

            response = requests.get(url, headers=headers, timeout=self.TIMEOUT)

            print(f"[APR-ALT] Response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"[APR-ALT] Response data: {data}")

                if data:
                    return CompanyData(
                        naziv=data.get('name') or data.get('naziv') or '',
                        pib=pib,
                        maticni_broj=data.get('mb') or data.get('maticniBroj') or data.get('maticni_broj'),
                        adresa=data.get('address') or data.get('adresa'),
                        mesto=data.get('city') or data.get('mesto') or data.get('grad'),
                        postanski_broj=data.get('zip') or data.get('postanskiBroj'),
                        email=data.get('email'),
                        delatnost=data.get('activity') or data.get('delatnost'),
                        status=data.get('status')
                    )

            return None

        except requests.RequestException as e:
            print(f"[APR-ALT] Request error: {str(e)}")
            return None
        except Exception as e:
            print(f"[APR-ALT] Error: {str(e)}")
            return None

    def _parse_apr_response(self, data: Dict, pib: str) -> CompanyData:
        """
        Parsira odgovor iz APR API-ja u CompanyData objekat.
        """
        # APR može vratiti različite strukture podataka
        # Pokušavamo da izvučemo podatke iz različitih polja

        naziv = (
            data.get('name') or
            data.get('naziv') or
            data.get('fullName') or
            data.get('poslovnoIme') or
            data.get('PoslovnoIme') or
            ''
        )

        maticni = (
            data.get('mb') or
            data.get('maticniBroj') or
            data.get('MaticniBroj') or
            data.get('registrationNumber') or
            None
        )

        adresa = (
            data.get('address') or
            data.get('adresa') or
            data.get('sediste') or
            data.get('Adresa') or
            None
        )

        mesto = (
            data.get('city') or
            data.get('mesto') or
            data.get('Mesto') or
            data.get('opstina') or
            None
        )

        postanski = (
            data.get('zip') or
            data.get('zipCode') or
            data.get('postanskiBroj') or
            None
        )

        status = (
            data.get('status') or
            data.get('Status') or
            data.get('statusPreduzeca') or
            None
        )

        return CompanyData(
            naziv=naziv,
            pib=pib,
            maticni_broj=maticni,
            adresa=adresa,
            mesto=mesto,
            postanski_broj=postanski,
            email=data.get('email'),
            delatnost=data.get('delatnost') or data.get('activity'),
            status=status
        )


# Singleton instanca servisa
apr_service = APRService()

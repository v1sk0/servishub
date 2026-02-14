"""
HerokuDomainService - Automatsko upravljanje custom domenima na Heroku platformi.

Koristi Heroku Platform API za:
- Dodavanje custom domena (POST /apps/{app}/domains)
- Brisanje custom domena (DELETE /apps/{app}/domains/{hostname})
- Proveru statusa domena (GET /apps/{app}/domains/{hostname})

Env varijable:
- SHUB_HEROKU_API_KEY: Bearer token za Heroku API
- SHUB_HEROKU_APP_NAME: Ime Heroku aplikacije (default: servicehubdolce)
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

HEROKU_API_URL = 'https://api.heroku.com'
HEROKU_HEADERS = {
    'Accept': 'application/vnd.heroku+json; version=3',
    'Content-Type': 'application/json',
}


class HerokuDomainService:
    """Upravlja custom domenima na Heroku platformi."""

    def __init__(self):
        self.api_key = os.environ.get('SHUB_HEROKU_API_KEY')
        self.app_name = os.environ.get('SHUB_HEROKU_APP_NAME', 'servicehubdolce')

    def _get_headers(self):
        """Vraća headers sa Authorization."""
        if not self.api_key:
            raise RuntimeError('SHUB_HEROKU_API_KEY env var nije podešen')
        return {
            **HEROKU_HEADERS,
            'Authorization': f'Bearer {self.api_key}',
        }

    def add_domain(self, hostname: str) -> dict:
        """
        Dodaje custom domen na Heroku aplikaciju.

        Args:
            hostname: Domen za dodavanje (npr. "mojservis.rs")

        Returns:
            {'success': True, 'cname_target': '...herokudns.com', 'status': '...'}
            ili {'success': False, 'error': '...'}
        """
        try:
            resp = requests.post(
                f'{HEROKU_API_URL}/apps/{self.app_name}/domains',
                headers=self._get_headers(),
                json={'hostname': hostname, 'sni_endpoint': None},
                timeout=15,
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                cname_target = data.get('cname') or data.get('cname_target', '')
                logger.info(f'Heroku domain added: {hostname} -> {cname_target}')
                return {
                    'success': True,
                    'cname_target': cname_target,
                    'status': data.get('status', 'created'),
                    'domain_id': data.get('id', ''),
                }

            # Domen već postoji na ovoj app-i
            if resp.status_code == 422:
                error_data = resp.json()
                error_msg = error_data.get('message', str(error_data))
                # Ako je "already added", probaj da dohvatiš info
                if 'already' in error_msg.lower():
                    logger.info(f'Domain {hostname} already exists on Heroku, fetching info')
                    return self.get_domain_info(hostname)
                logger.warning(f'Heroku domain add failed (422): {error_msg}')
                return {'success': False, 'error': error_msg}

            logger.error(f'Heroku domain add failed ({resp.status_code}): {resp.text}')
            return {'success': False, 'error': f'Heroku API error: {resp.status_code}'}

        except requests.exceptions.Timeout:
            logger.error(f'Heroku API timeout adding domain: {hostname}')
            return {'success': False, 'error': 'Heroku API timeout'}
        except RuntimeError as e:
            logger.error(str(e))
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f'Heroku domain add error: {e}')
            return {'success': False, 'error': f'Unexpected error: {str(e)}'}

    def remove_domain(self, hostname: str) -> dict:
        """
        Uklanja custom domen sa Heroku aplikacije.

        Args:
            hostname: Domen za brisanje

        Returns:
            {'success': True} ili {'success': False, 'error': '...'}
        """
        try:
            resp = requests.delete(
                f'{HEROKU_API_URL}/apps/{self.app_name}/domains/{hostname}',
                headers=self._get_headers(),
                timeout=15,
            )

            if resp.status_code in (200, 204):
                logger.info(f'Heroku domain removed: {hostname}')
                return {'success': True}

            if resp.status_code == 404:
                logger.info(f'Domain {hostname} not found on Heroku (already removed)')
                return {'success': True}  # Već obrisan, nije greška

            logger.error(f'Heroku domain remove failed ({resp.status_code}): {resp.text}')
            return {'success': False, 'error': f'Heroku API error: {resp.status_code}'}

        except requests.exceptions.Timeout:
            logger.error(f'Heroku API timeout removing domain: {hostname}')
            return {'success': False, 'error': 'Heroku API timeout'}
        except RuntimeError as e:
            logger.error(str(e))
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f'Heroku domain remove error: {e}')
            return {'success': False, 'error': f'Unexpected error: {str(e)}'}

    def get_domain_info(self, hostname: str) -> dict:
        """
        Dohvata informacije o domenu sa Heroku-a.

        Args:
            hostname: Domen za proveru

        Returns:
            {'success': True, 'cname_target': '...', 'status': '...'} ili {'success': False, ...}
        """
        try:
            resp = requests.get(
                f'{HEROKU_API_URL}/apps/{self.app_name}/domains/{hostname}',
                headers=self._get_headers(),
                timeout=15,
            )

            if resp.status_code == 200:
                data = resp.json()
                cname_target = data.get('cname') or data.get('cname_target', '')
                return {
                    'success': True,
                    'cname_target': cname_target,
                    'status': data.get('status', 'unknown'),
                    'domain_id': data.get('id', ''),
                }

            if resp.status_code == 404:
                return {'success': False, 'error': 'Domain not found on Heroku'}

            return {'success': False, 'error': f'Heroku API error: {resp.status_code}'}

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Heroku API timeout'}
        except RuntimeError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': f'Unexpected error: {str(e)}'}


# Singleton instanca
heroku_domain_service = HerokuDomainService()

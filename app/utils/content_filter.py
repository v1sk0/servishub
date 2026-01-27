"""
Content filter - filtrira kontakt informacije iz poruka pre reveal-a.

Filtrira: telefone, email adrese, URL-ove.
"""

import re


# Regex paterne za kontakt info
_PHONE_PATTERN = re.compile(
    r'(?:\+?\d{1,3}[\s\-]?)?'   # country code
    r'(?:\(?\d{2,4}\)?[\s\-]?)'  # area code
    r'(?:\d[\s\-]?){5,10}',      # number
    re.MULTILINE
)

_EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.MULTILINE
)

_URL_PATTERN = re.compile(
    r'(?:https?://|www\.)[^\s<>\"\')]+',
    re.MULTILINE | re.IGNORECASE
)

# Fajl ekstenzije zabranjene pre reveal-a
BLOCKED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.vcf', '.xls', '.xlsx'}


def filter_contact_info(text):
    """
    Filtrira kontakt informacije iz teksta.

    Returns:
        Filtrirani tekst sa zamenjenim kontakt podacima.
    """
    if not text:
        return text

    text = _EMAIL_PATTERN.sub('[email uklonjen]', text)
    text = _URL_PATTERN.sub('[link uklonjen]', text)
    text = _PHONE_PATTERN.sub('[telefon uklonjen]', text)
    return text


def is_blocked_file_extension(filename):
    """Proveri da li je fajl ekstenzija blokirana pre reveal-a."""
    if not filename:
        return False
    ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in BLOCKED_EXTENSIONS
"""
File Security Utilities.

Validacija uploadovanih fajlova:
- MIME type checking (magic bytes)
- Executable detection
- Size limits
- Filename sanitization

VAZNO: Ove provere se koriste za sve file upload-e u aplikaciji,
ukljucujuci bank import, KYC dokumente, i attachments.
"""

import re
import logging
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)


# ========================
# ALLOWED MIME TYPES
# ========================

ALLOWED_MIMES = {
    # Text/Data files
    'csv': ['text/csv', 'text/plain', 'application/csv'],
    'xml': ['text/xml', 'application/xml'],
    'txt': ['text/plain'],
    'json': ['application/json', 'text/plain'],

    # Documents
    'pdf': ['application/pdf'],

    # Office documents (koriste ZIP format interno)
    'xlsx': [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/zip',
        'application/octet-stream'
    ],
    'xls': ['application/vnd.ms-excel', 'application/octet-stream'],
    'ods': [
        'application/vnd.oasis.opendocument.spreadsheet',
        'application/zip'
    ],
    'docx': [
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/zip'
    ],

    # Images
    'png': ['image/png'],
    'jpg': ['image/jpeg'],
    'jpeg': ['image/jpeg'],
    'gif': ['image/gif'],
    'webp': ['image/webp'],
}


# ========================
# DANGEROUS SIGNATURES
# ========================

# Magic bytes za executable i opasne fajlove
DANGEROUS_SIGNATURES = [
    b'\x4d\x5a',              # MZ - Windows PE executable
    b'\x7f\x45\x4c\x46',      # ELF - Linux executable
    b'#!/',                   # Shebang (shell script)
    b'<%',                    # ASP/JSP
    b'<?php',                 # PHP
    b'<script',               # JavaScript in HTML
    b'<html',                 # HTML (moze sadrzati malicious JS)
    b'<svg',                  # SVG (moze sadrzati JS)
]

# Office formati koriste ZIP, pa ih ne blokirati samo zbog ZIP signature
# Umesto toga, proveravamo specifican sadrzaj


def validate_file_mime(file_content: bytes, expected_extension: str) -> Tuple[bool, str]:
    """
    Validira da MIME tip fajla odgovara ocekivanoj ekstenziji.

    Koristi python-magic ako je dostupan, inace filetype,
    inace fallback na ekstenziju.

    Args:
        file_content: Raw bytes sadrzaja fajla
        expected_extension: Ocekivana ekstenzija (bez tacke)

    Returns:
        (is_valid: bool, detected_mime: str)
    """
    detected_mime = None

    # Probaj python-magic (najbolja detekcija)
    try:
        import magic
        detected_mime = magic.from_buffer(file_content, mime=True)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"python-magic failed: {e}")

    # Fallback na filetype library
    if detected_mime is None:
        try:
            import filetype
            kind = filetype.guess(file_content)
            detected_mime = kind.mime if kind else None
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"filetype failed: {e}")

    # Poslednji fallback - veruj ekstenziji ali loguj warning
    if detected_mime is None:
        logger.warning(f"No MIME detection library available, trusting extension: {expected_extension}")
        return True, 'unknown'

    # Proveri da li je detektovani MIME u dozvoljenim za tu ekstenziju
    ext_lower = expected_extension.lower().lstrip('.')
    allowed = ALLOWED_MIMES.get(ext_lower, [])

    is_valid = detected_mime in allowed
    if not is_valid:
        logger.warning(
            f"MIME mismatch: expected one of {allowed} for .{ext_lower}, "
            f"but detected {detected_mime}"
        )

    return is_valid, detected_mime


def check_no_executable(file_content: bytes) -> bool:
    """
    Proveri da fajl ne sadrzi executable signature.

    NAPOMENA: Ova funkcija proverava samo pocetak fajla.
    Za kompletnu analizu, koristiti antivirus/sandbox.

    Args:
        file_content: Raw bytes

    Returns:
        True ako je fajl SIGURAN (nema executable signature)
    """
    # Proveri prvih 100 bajtova
    header = file_content[:100]

    for sig in DANGEROUS_SIGNATURES:
        if sig in header:
            logger.warning(f"Dangerous signature detected: {sig[:10]}...")
            return False

    return True


def check_office_document_safety(file_content: bytes, extension: str) -> bool:
    """
    Dodatna provera za Office dokumente.

    Office fajlovi (xlsx, docx) su ZIP arhive. Ova funkcija
    proverava da ne sadrze macro-e ili embedded executable.

    Args:
        file_content: Raw bytes
        extension: Ekstenzija fajla

    Returns:
        True ako je fajl SIGURAN
    """
    ext_lower = extension.lower().lstrip('.')

    # Samo za Office formate
    if ext_lower not in ['xlsx', 'xls', 'docx', 'doc', 'ods']:
        return True

    try:
        import zipfile
        from io import BytesIO

        # xlsx/docx su ZIP fajlovi
        if ext_lower in ['xlsx', 'docx', 'ods']:
            zf = zipfile.ZipFile(BytesIO(file_content))

            # Proveri za macro-e
            dangerous_files = [
                'xl/vbaProject.bin',      # Excel VBA
                'word/vbaProject.bin',    # Word VBA
                'xl/macrosheets/',        # Excel 4.0 macro sheets
            ]

            for name in zf.namelist():
                for dangerous in dangerous_files:
                    if dangerous in name:
                        logger.warning(f"Office document contains macros: {name}")
                        return False

    except zipfile.BadZipFile:
        # Nije validan ZIP - moze biti xls/doc (stariji format)
        pass
    except Exception as e:
        logger.warning(f"Office document check failed: {e}")

    return True


def validate_file_size(file_content: bytes, max_size_mb: int = 10) -> bool:
    """
    Proveri da fajl nije prevelik.

    Args:
        file_content: Raw bytes
        max_size_mb: Maksimalna velicina u MB

    Returns:
        True ako je velicina OK
    """
    max_bytes = max_size_mb * 1024 * 1024
    actual_size = len(file_content)

    if actual_size > max_bytes:
        logger.warning(f"File too large: {actual_size} bytes > {max_bytes} bytes")
        return False

    return True


def sanitize_filename(filename: str) -> str:
    """
    Sanitizuj filename - ukloni opasne karaktere.

    Ova funkcija:
    - Uklanja path separatore (sprecava directory traversal)
    - Zadrzava samo alphanumeric, tacku, minus, underscore
    - Sprecava hidden files (pocinje sa tackom)
    - Ogranicava duzinu na 255 karaktera

    Args:
        filename: Originalni filename

    Returns:
        Sanitizovani filename
    """
    if not filename:
        return 'unnamed'

    # Ukloni path separatore
    filename = filename.replace('/', '_').replace('\\', '_')

    # Zadrzi samo safe karaktere
    filename = re.sub(r'[^\w\.\-]', '_', filename)

    # Spreci hidden files
    if filename.startswith('.'):
        filename = '_' + filename

    # Spreci double dots (directory traversal)
    while '..' in filename:
        filename = filename.replace('..', '_')

    # Ogranici duzinu
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_len = 255 - len(ext) - 1 if ext else 255
        filename = name[:max_name_len] + ('.' + ext if ext else '')

    return filename


def validate_upload(
    file_content: bytes,
    filename: str,
    allowed_extensions: Optional[List[str]] = None,
    max_size_mb: int = 10,
    check_executable: bool = True,
    check_office_macros: bool = True
) -> Tuple[bool, str, str]:
    """
    Kompletna validacija uploadovanog fajla.

    Ovo je glavna funkcija koju treba koristiti za validaciju upload-a.

    Args:
        file_content: Raw bytes sadrzaja fajla
        filename: Originalni filename
        allowed_extensions: Lista dozvoljenih ekstenzija (None = sve iz ALLOWED_MIMES)
        max_size_mb: Max velicina u MB
        check_executable: Da li proveravati za executable signatures
        check_office_macros: Da li proveravati Office dokumente za macro-e

    Returns:
        (is_valid: bool, error_message: str, safe_filename: str)
    """
    # 1. Sanitize filename
    safe_filename = sanitize_filename(filename)

    # 2. Proveri ekstenziju
    if '.' not in safe_filename:
        return False, 'Fajl mora imati ekstenziju', safe_filename

    extension = safe_filename.rsplit('.', 1)[-1].lower()

    if allowed_extensions:
        allowed_lower = [e.lower().lstrip('.') for e in allowed_extensions]
        if extension not in allowed_lower:
            return False, f'Nedozvoljena ekstenzija: .{extension}', safe_filename
    elif extension not in ALLOWED_MIMES:
        return False, f'Nepoznata ekstenzija: .{extension}', safe_filename

    # 3. Proveri velicinu
    if not validate_file_size(file_content, max_size_mb):
        return False, f'Fajl je prevelik (max {max_size_mb}MB)', safe_filename

    # 4. Proveri MIME tip
    is_valid_mime, detected_mime = validate_file_mime(file_content, extension)
    if not is_valid_mime:
        return False, f'Tip fajla ({detected_mime}) ne odgovara ekstenziji (.{extension})', safe_filename

    # 5. Proveri za executable
    if check_executable and not check_no_executable(file_content):
        return False, 'Detektovan potencijalno opasan fajl', safe_filename

    # 6. Proveri Office dokumente za macro-e
    if check_office_macros and not check_office_document_safety(file_content, extension):
        return False, 'Office dokument sadrzi macro-e koji nisu dozvoljeni', safe_filename

    return True, '', safe_filename

"""
Bank Parser Registry.

Auto-detektuje banku iz fajla i koristi odgovarajući parser.
"""
from typing import Dict, Type, Optional

from .base import BaseBankParser, ParseResult
from .alta import AltaBankParser


# Registry svih parsera
PARSERS: Dict[str, Type[BaseBankParser]] = {
    'ALTA': AltaBankParser,
    # Dodati ostale parsere kad budu implementirani:
    # 'RAIF': RaiffeisenParser,
    # 'ERST': ErsteParser,
    # 'AIK': AIKParser,
    # 'NLB': NLBParser,
    # 'INT': IntesaParser,
}


def detect_bank_and_parse(
    content: bytes,
    filename: str,
    force_bank: Optional[str] = None
) -> dict:
    """
    Detektuje banku i parsira izvod.

    Args:
        content: Raw file bytes
        filename: Original filename
        force_bank: Force specific bank code (skip detection)

    Returns:
        ParseResult.to_dict()

    Raises:
        ValueError: If bank cannot be detected or parsed
    """
    if force_bank:
        if force_bank not in PARSERS:
            raise ValueError(f'Unknown bank code: {force_bank}')
        parser = PARSERS[force_bank]()
        result = parser.parse(content, filename)
        return result.to_dict()

    # Auto-detect
    for bank_code, parser_class in PARSERS.items():
        parser = parser_class()
        if parser.can_parse(content, filename):
            result = parser.parse(content, filename)
            return result.to_dict()

    raise ValueError(
        'Could not detect bank from file. '
        'Please specify bank_code manually or check file format.'
    )


def get_supported_banks() -> list:
    """Vraća listu podržanih banaka."""
    return [
        {
            'code': code,
            'name': parser_class.BANK_NAME
        }
        for code, parser_class in PARSERS.items()
    ]
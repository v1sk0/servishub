"""
Typing Status Service - Real-time typing indicators.

In-memory storage for typing status. Status expires after 3 seconds.
"""

from datetime import datetime, timezone


# Global typing status storage
# Format: {thread_id: {user_key: {'name': 'Ime', 'type': 'tenant'|'admin', 'expires': timestamp}}}
_typing_status = {}


def clean_expired():
    """Uklanja istekle typing statuse."""
    now = datetime.now(timezone.utc).timestamp()
    for thread_id in list(_typing_status.keys()):
        for user_key in list(_typing_status[thread_id].keys()):
            if _typing_status[thread_id][user_key]['expires'] < now:
                del _typing_status[thread_id][user_key]
        if not _typing_status[thread_id]:
            del _typing_status[thread_id]


def set_typing(thread_id: int, user_key: str, name: str, user_type: str, is_typing: bool = True):
    """
    Postavlja typing status za korisnika.

    Args:
        thread_id: ID threada
        user_key: Jedinstveni kljuc (npr. 'tenant_123' ili 'admin_456')
        name: Ime korisnika za prikaz
        user_type: 'tenant' ili 'admin'
        is_typing: True ako kuca, False ako prestao
    """
    clean_expired()

    if is_typing:
        if thread_id not in _typing_status:
            _typing_status[thread_id] = {}
        _typing_status[thread_id][user_key] = {
            'name': name,
            'type': user_type,
            'expires': datetime.now(timezone.utc).timestamp() + 3  # Istice za 3s
        }
    else:
        if thread_id in _typing_status and user_key in _typing_status[thread_id]:
            del _typing_status[thread_id][user_key]


def get_typing(thread_id: int, exclude_key: str = None) -> list:
    """
    Vraća listu korisnika koji trenutno kucaju u threadu.

    Args:
        thread_id: ID threada
        exclude_key: Kljuc korisnika koji ne treba da se prikaze (npr. sebe)

    Returns:
        Lista dict-ova sa 'name' i 'type' za svakog ko kuca
    """
    clean_expired()

    typing_users = []
    if thread_id in _typing_status:
        for user_key, info in _typing_status[thread_id].items():
            if exclude_key and user_key == exclude_key:
                continue
            typing_users.append({
                'name': info['name'],
                'type': info['type']
            })

    return typing_users
"""
Kurirske sluzbe u Srbiji - staticni recnik za dropdown i tracking.
"""

COURIER_SERVICES = {
    'd_express': {
        'name': 'D Express',
        'tracking_url': 'https://www.dexpress.rs/rs/pracenje-posiljke.html?id={tracking}',
    },
    'aks': {
        'name': 'AKS Express',
        'tracking_url': 'https://www.aks.rs/pracenje/?broj={tracking}',
    },
    'bex': {
        'name': 'BEX Express',
        'tracking_url': 'https://bfrigo.com/pracenje/{tracking}',
    },
    'post_express': {
        'name': 'Post Express',
        'tracking_url': 'https://www.postexpress.rs/pracenje-posiljke/{tracking}',
    },
    'city_express': {
        'name': 'City Express',
        'tracking_url': 'https://cityexpress.rs/pracenje/{tracking}',
    },
    'ysk': {
        'name': 'YSK Logistics',
    },
    'dhl': {
        'name': 'DHL Express',
        'tracking_url': 'https://www.dhl.com/rs-sr/home/tracking.html?tracking-id={tracking}',
    },
}


def get_courier_list():
    """Vraca listu kurirskih sluzbi za dropdown: [{id, name}]."""
    return [
        {'id': key, 'name': val['name']}
        for key, val in COURIER_SERVICES.items()
    ]


def get_tracking_url(courier_id, tracking_number):
    """
    Generise tracking URL za datu kurirsku sluzbu i broj posiljke.
    Vraca None ako kurirska sluzba nema tracking URL.
    """
    courier = COURIER_SERVICES.get(courier_id)
    if not courier or 'tracking_url' not in courier or not tracking_number:
        return None
    return courier['tracking_url'].replace('{tracking}', str(tracking_number))

"""
Flash Services - Predefinisane usluge za animirani tekst na javnoj stranici.

Ove usluge se prikazuju u "scramble reveal" animaciji koja rotira kroz
različite usluge servisa kako bi privukla pažnju posetilaca.
"""

# Usluge grupisane po kategorijama
FLASH_SERVICES = {
    'telefoni': [
        'Zamena ekrana',
        'Zamena baterije',
        'Zamena konektora punjenja',
        'Vađenje podataka',
        'Otključavanje telefona',
        'Popravka matične ploče',
        'Zamena kamere',
        'Zamena zvučnika',
    ],
    'racunari': [
        'Zamena tastature',
        'Zamena napajanja',
        'Čišćenje od virusa',
        'Zamena HDD/SSD',
        'Nadogradnja RAM-a',
        'Reinstalacija sistema',
        'Popravka ekrana laptopa',
        'Zamena ventilatora',
    ],
    'konzole': [
        'Zamena joystick-a',
        'Popravka HDMI porta',
        'Čišćenje i termalna pasta',
        'Zamena optičkog drajva',
        'Reballing čipa',
    ],
    'trotineti': [
        'Zamena baterije',
        'Popravka kontrolera',
        'Zamena guma',
        'Popravka kočnica',
        'Zamena motora',
    ],
    'ostalo': [
        'Popravka tableta',
        'Popravka smart satova',
        'Popravka slušalica',
        'Popravka dronova',
    ]
}

# Prednosti servisa - uvek se prikazuju
FLASH_BENEFITS = [
    'Servis u najkraćem roku',
    'Originalni delovi',
    'Iskusni serviseri',
    'Praćenje garancije online',
    'Garancija na sve popravke',
]

# Default kategorije koje su uključene
DEFAULT_FLASH_CATEGORIES = {
    'telefoni': True,
    'racunari': True,
    'konzole': False,
    'trotineti': False,
    'ostalo': False
}


# Redosled kategorija za prikaz (telefoni prvi, pa računari, pa ostalo)
CATEGORY_ORDER = ['telefoni', 'racunari', 'konzole', 'trotineti', 'ostalo']


def get_flash_words(categories: dict = None) -> list:
    """
    Vraća listu reči za flash animaciju na osnovu uključenih kategorija.

    Redosled: telefoni → računari → konzole → trotineti → ostalo → prednosti

    Args:
        categories: Dict sa boolean vrednostima za svaku kategoriju.
                   Ako je None, koriste se default vrednosti.

    Returns:
        Lista reči (usluge po redosledu kategorija + prednosti na kraju)
    """
    if categories is None:
        categories = DEFAULT_FLASH_CATEGORIES

    words = []

    # Dodaj usluge po definisanom redosledu kategorija
    for cat in CATEGORY_ORDER:
        if categories.get(cat, False) and cat in FLASH_SERVICES:
            words.extend(FLASH_SERVICES[cat])

    # Prednosti na kraju
    words.extend(FLASH_BENEFITS)

    return words

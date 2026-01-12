# ServisHub

SaaS platforma za servise mobilnih telefona.

## Setup

```bash
git clone https://github.com/v1sk0/servishub.git && cd servishub
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt && flask db upgrade && python run.py
```

## Stack

Python 3.11 | Flask | SQLAlchemy | PostgreSQL | Tailwind | Alpine.js | JWT

## API (115 ruta)

- `/api/v1/*` - Tenant (65)
- `/api/admin/*` - Admin (21)
- `/api/supplier/*` - Supplier (22)
- `/api/public/*` - Public (7)

## Cene

3 meseca free → 3,600 RSD/mes + 1,800/lokacija

---

Za AI agente: [CLAUDE.md](CLAUDE.md)

# QueryVault — Save & Search Your SQL Snippets (Django)

A tiny Django system to save your ready-made queries/snippets and find them later by keywords, tags, or full-text search.

## Features
- Save snippets: title, description, SQL text, tags, DB type.
- Search by keyword across title/description/tags/SQL.
- Postgres Full‑Text Search (if available) or fallback to `icontains` for SQLite/MySQL.
- REST API (DRF) for CRUD and search.
- Simple web UI (list/search/create/edit/view).
- Auth: login required for write; anonymous can read (configurable).

## Quickstart (SQLite, dev)
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```
Open: http://127.0.0.1:8000/

## Postgres FTS (optional)
If using Postgres, set env vars and add `DATABASES` in settings accordingly. The app will try to use `django.contrib.postgres.search` if available.

## API
- `GET /api/snippets/` list (filters: `q`, `tag`, `db_type`)
- `POST /api/snippets/` create
- `GET /api/snippets/{id}/` retrieve
- `PUT/PATCH /api/snippets/{id}/` update
- `DELETE /api/snippets/{id}/` delete
- `GET /api/search/?q=...` search

## Import/Export
- Export all: `python manage.py dumpdata vault.QuerySnippet --indent 2 > snippets.json`
- Import: `python manage.py loaddata snippets.json`

## Notes
- For MySQL/SQLite, search uses `icontains`. For Postgres, FTS with rank ordering if enabled.
- Adjust permission logic in `vault/views.py` & `vault/serializers.py` as you like.

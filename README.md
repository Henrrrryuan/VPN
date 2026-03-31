# VPN SaaS MVP (Flask + SQLite + x-ui)

This is a stage-1/2 MVP backend for:
- User register/login
- Auto UUID provisioning
- Auto calling x-ui API to create VLESS user
- Returning token + VLESS/subscription info
- JWT protected profile API + simple dashboard page
- Multi-node support (SG/JP) with user node switching

## Project structure

```txt
.
├── app
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models.py
│   ├── routes
│   │   ├── auth.py
│   │   └── pages.py
│   └── services
│       ├── auth_service.py
│       └── xui_client.py
├── templates
│   ├── dashboard.html
│   └── index.html
├── .env.example
├── requirements.txt
└── run.py
```

## Quick start

1. Create and activate virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure env:

```bash
cp .env.example .env
```

Then edit `.env`:
- `SECRET_KEY`: set a strong random string
- `NODES_JSON`: set at least one node config (recommended with SG + JP)

4. Run app:

```bash
python run.py
```

Server starts at `http://127.0.0.1:5000`.

## API examples

### Register

```bash
curl -X POST http://127.0.0.1:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username":"alice",
    "email":"alice@example.com",
    "password":"12345678"
  }'
```

### Login

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "identity":"alice",
    "password":"12345678"
  }'
```

### Get current user profile (`/api/auth/me`)

```bash
curl http://127.0.0.1:5000/api/auth/me \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

### List enabled nodes

```bash
curl http://127.0.0.1:5000/api/nodes \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

### Switch node

```bash
curl -X POST http://127.0.0.1:5000/api/nodes/select \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -d '{"node_id": 2}'
```

## Pages

- `/` login/register page
- `/dashboard` user panel page (reads JWT from browser localStorage, supports node switching)

## Notes

- SQLite is enough for MVP. Move to MySQL/PostgreSQL later.
- In some x-ui versions, direct subscription URL may not be returned by `getClientTraffics`. This project now falls back to building a standard VLESS Reality link from inbound config.

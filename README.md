# OpsGuard AI

OpsGuard AI est une plateforme de revue documentaire IA sécurisée, construite progressivement comme projet portfolio backend/IA. Le but est de démontrer une architecture web maintenable, testable et orientée sécurité pour l'ingestion, la recherche et la revue de documents sensibles.

Le projet ne fait pas encore de RAG ni d'analyse IA. Le bloc actuel stabilise une base saine: API FastAPI, validation Pydantic, persistance PostgreSQL, documentation et tests de base.

## État actuel

Ce qui existe aujourd'hui:

- un monorepo avec `apps/api` et `apps/web`;
- une API FastAPI avec `GET /health`;
- un modèle `Document` SQLAlchemy;
- des schemas Pydantic pour créer et lire des documents;
- `POST /documents` pour créer une entrée documentaire;
- `GET /documents` pour lister les documents;
- une base PostgreSQL locale lancée avec Docker Compose;
- l'image PostgreSQL `pgvector/pgvector:pg16`;
- l'extension `vector` activée au démarrage de l'API;
- un frontend Next.js minimal;
- des tests pytest pour `/health` et le workflow create/list documents.

Ce qui n'existe pas encore:

- upload réel de PDF;
- parsing PDF ou Markdown;
- extraction de texte;
- chunking;
- embeddings;
- colonnes vectorielles ou recherche sémantique;
- RAG ou réponses avec citations;
- intégration OpenAI, Anthropic ou autre fournisseur IA;
- authentification, rôles ou isolation tenant;
- migrations Alembic;
- dashboard frontend complet;
- CI complète.

## Stack actuelle

- Python
- FastAPI
- uv
- SQLAlchemy
- Pydantic
- pydantic-settings
- psycopg
- PostgreSQL
- pgvector
- Docker Compose
- Next.js
- TypeScript
- Tailwind
- pnpm
- pytest
- ruff
- mypy

## Architecture actuelle

Flux principal:

```text
Client / Frontend
-> FastAPI
-> Pydantic schema DocumentCreate
-> route POST /documents
-> service create_document
-> modèle SQLAlchemy Document
-> session SQLAlchemy
-> psycopg
-> PostgreSQL dans Docker
-> réponse formatée avec DocumentRead
```

La logique HTTP reste dans les routes FastAPI. La logique applicative simple est placée dans les services. Les modèles SQLAlchemy décrivent la structure persistée en base, tandis que les schemas Pydantic décrivent les contrats d'entrée et de sortie de l'API.

Voir aussi [docs/architecture.md](docs/architecture.md).

## Prérequis

- Python 3.12 ou plus récent
- uv
- Docker et Docker Compose
- Node.js compatible avec Next.js
- pnpm

## Installation

Depuis la racine du repository:

```bash
cp .env.example .env
```

Installer les dépendances backend:

```bash
cd apps/api
uv sync
```

Installer les dépendances frontend:

```bash
cd apps/web
pnpm install
```

## Configuration

La configuration locale est lue depuis `.env` à la racine du projet.

Exemple:

```env
POSTGRES_DB=opsguard_ai
POSTGRES_USER=opsguard
POSTGRES_PASSWORD=change-me-local-only
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

DATABASE_URL=postgresql+psycopg://opsguard:change-me-local-only@localhost:5432/opsguard_ai
```

Ne commit jamais de vrais secrets dans `.env`. Le fichier `.env.example` sert uniquement de modèle local.

## Lancer PostgreSQL

Depuis la racine du repository:

```bash
docker compose up -d postgres
```

Pour vérifier l'état du service:

```bash
docker compose ps
```

La base utilise un volume Docker nommé `opsguard_postgres_data`.

## Lancer le backend

Dans `apps/api`:

```bash
uv run uvicorn opsguard_api.main:app --reload
```

L'API est disponible par défaut sur:

```text
http://127.0.0.1:8000
```

Au démarrage, l'API initialise temporairement les tables avec `SQLAlchemy.create_all()` et active l'extension PostgreSQL `vector` si le dialecte est PostgreSQL.

## Lancer le frontend

Dans `apps/web`:

```bash
pnpm dev
```

Le frontend est disponible par défaut sur:

```text
http://localhost:3000
```

Le frontend est minimal pour le moment et ne couvre pas encore un dashboard documentaire complet.

## Lancer les tests et outils qualité

Dans `apps/api`:

```bash
uv run pytest
uv run ruff check .
uv run mypy
```

Les tests actuels supposent une base PostgreSQL locale accessible via `DATABASE_URL`.

## Endpoints actuels

### `GET /health`

Retourne l'état minimal de l'API.

Réponse:

```json
{
  "status": "ok"
}
```

### `POST /documents`

Crée une entrée documentaire en base. Cette route ne téléverse pas encore de fichier.

Payload exemple:

```json
{
  "title": "NIST Incident Response Guide",
  "source_type": "public_pdf",
  "source_path": "data/raw/nist-incident-response-guide.pdf"
}
```

Réponse exemple:

```json
{
  "id": 1,
  "title": "NIST Incident Response Guide",
  "source_type": "public_pdf",
  "source_path": "data/raw/nist-incident-response-guide.pdf",
  "status": "uploaded",
  "created_at": "2026-06-09T12:00:00Z",
  "updated_at": "2026-06-09T12:00:00Z"
}
```

### `GET /documents`

Liste les documents persistés, triés du plus récent au plus ancien.

Réponse exemple:

```json
[
  {
    "id": 1,
    "title": "NIST Incident Response Guide",
    "source_type": "public_pdf",
    "source_path": "data/raw/nist-incident-response-guide.pdf",
    "status": "uploaded",
    "created_at": "2026-06-09T12:00:00Z",
    "updated_at": "2026-06-09T12:00:00Z"
  }
]
```

## Roadmap courte

Prochains blocs prévus:

1. Remplacer `create_all()` par Alembic avant de complexifier le schéma.
2. Ajouter l'upload réel de documents.
3. Extraire le texte des fichiers supportés.
4. Introduire le chunking et le stockage des chunks.
5. Ajouter les embeddings et une première recherche sémantique avec pgvector.
6. Construire une réponse avec citations.
7. Ajouter les premières tâches de revue et les contrôles de sécurité.

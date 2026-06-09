# OpsGuard AI

OpsGuard AI est une plateforme de revue documentaire IA sécurisée, construite progressivement comme projet portfolio backend/IA. Le but est de démontrer une architecture web maintenable, testable et orientée sécurité pour l'ingestion, la recherche et la revue de documents sensibles.

Le projet ne fait pas encore de RAG ni d'analyse IA. Le bloc actuel stabilise une base saine: API FastAPI, upload local de documents, extraction de texte minimale, chunking structure-aware, validation Pydantic, persistance PostgreSQL, documentation et tests de base.

## État actuel

Ce qui existe aujourd'hui:

- un monorepo avec `apps/api` et `apps/web`;
- une API FastAPI avec `GET /health`;
- un modèle `Document` SQLAlchemy;
- un modèle `DocumentChunk` SQLAlchemy;
- des schemas Pydantic pour créer et lire des documents;
- `POST /documents` pour créer une entrée documentaire;
- `POST /documents/upload` pour téléverser un PDF, Markdown ou texte brut localement;
- `POST /documents/{document_id}/extract-text` pour extraire le texte d'un document uploadé;
- `POST /documents/{document_id}/chunk` pour découper le texte extrait en chunks;
- `GET /documents/{document_id}/chunks` pour inspecter les chunks d'un document;
- `GET /documents` pour lister les documents;
- une configuration locale de dossier d'upload, dossier d'extraction, taille maximale et limites de chunking;
- une base PostgreSQL locale lancée avec Docker Compose;
- l'image PostgreSQL `pgvector/pgvector:pg16`;
- l'extension `vector` activée au démarrage de l'API;
- un frontend Next.js minimal;
- des tests pytest pour `/health`, les documents, l'upload et l'extraction.

Ce qui n'existe pas encore:

- OCR pour les PDF scannés;
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
- pypdf
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

UPLOAD_DIR=data/uploads
EXTRACTED_TEXT_DIR=data/extracted
MAX_UPLOAD_SIZE_MB=10
CHUNK_MAX_CHARS=1200
CHUNK_OVERLAP_CHARS=150
```

Ne commit jamais de vrais secrets dans `.env`. Le fichier `.env.example` sert uniquement de modèle local.
Les fichiers téléversés sont sauvegardés localement dans `UPLOAD_DIR`. Les textes extraits sont sauvegardés dans `EXTRACTED_TEXT_DIR`. Les fichiers générés dans `data/uploads/` et `data/extracted/` sont ignorés par Git.
`CHUNK_MAX_CHARS` et `CHUNK_OVERLAP_CHARS` contrôlent la taille des chunks créés depuis le texte extrait. L'overlap est surtout utilisé lorsque le backend doit couper un bloc trop long.

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

### `POST /documents/upload`

Téléverse un fichier PDF, Markdown ou texte brut, le sauvegarde dans un dossier local contrôlé, puis crée une entrée documentaire avec `source_type = "uploaded_file"` et `status = "uploaded"`.

Form-data:

- `file`: fichier obligatoire;
- `title`: titre optionnel. Si absent, le nom original du fichier est utilisé comme titre.

Types acceptés:

- `.pdf` avec `application/pdf`;
- `.md` avec `text/markdown` ou `text/plain`;
- `.txt` avec `text/plain`.

Réponse exemple:

```json
{
  "id": 2,
  "title": "security-policy.md",
  "source_type": "uploaded_file",
  "source_path": "data/uploads/9e1b6c77c8b84a089ec77ccfba3d260a.md",
  "status": "uploaded",
  "created_at": "2026-06-09T12:05:00Z",
  "updated_at": "2026-06-09T12:05:00Z"
}
```

### `POST /documents/{document_id}/extract-text`

Extrait le texte d'un document uploadé depuis son `source_path` déjà enregistré en base. Le backend ne prend pas de chemin client arbitraire, vérifie que le fichier source est dans `UPLOAD_DIR`, puis sauvegarde le texte extrait dans `EXTRACTED_TEXT_DIR`.

Réponse exemple:

```json
{
  "document_id": 2,
  "status": "text_extracted",
  "extracted_text_path": "data/extracted/document-2.txt",
  "character_count": 1284,
  "message": "Text extracted successfully."
}
```

L'extraction supporte Markdown, texte brut et PDF avec texte extractible via `pypdf`. Il n'y a pas d'OCR, d'embeddings ou d'appel LLM dans ce bloc.

### `POST /documents/{document_id}/chunk`

Découpe le texte extrait d'un document en chunks structure-aware. Le document doit déjà avoir un texte extrait. Le backend relit le fichier contrôlé `EXTRACTED_TEXT_DIR/document-{document_id}.txt`, détecte les sections simples, regroupe les blocs logiques, supprime les anciens chunks du document, puis recrée une liste ordonnée de chunks.

Réponse exemple:

```json
{
  "document_id": 2,
  "status": "chunked",
  "chunk_count": 4,
  "chunk_max_chars": 1200,
  "chunk_overlap_chars": 150,
  "message": "Document chunked successfully."
}
```

En cas de succès, le statut du document passe à `chunked`. En cas d'échec après le début du chunking, il passe à `chunking_failed`.

### `GET /documents/{document_id}/chunks`

Retourne les chunks persistés d'un document, ordonnés par `chunk_index`. Cet endpoint sert surtout au debug et aux tests tant que l'interface documentaire complète n'existe pas encore.

Réponse exemple:

```json
[
  {
    "id": 1,
    "document_id": 2,
    "chunk_index": 0,
    "content": "Section: Security Policy\n\nAccess is reviewed quarterly.",
    "character_count": 62,
    "section_title": "Security Policy",
    "start_char": 19,
    "end_char": 50,
    "created_at": "2026-06-09T12:10:00Z"
  }
]
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
2. Ajouter les embeddings et une première recherche sémantique avec pgvector.
3. Construire une réponse avec citations.
4. Ajouter les premières tâches de revue et les contrôles de sécurité.

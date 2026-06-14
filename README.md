# OpsGuard AI

OpsGuard AI est une plateforme de revue documentaire IA sécurisée, construite progressivement comme projet portfolio backend/IA. Le but est de démontrer une architecture web maintenable, testable et orientée sécurité pour l'ingestion, la recherche et la revue de documents sensibles.

Le projet possède maintenant un premier bloc RAG backend: ingestion documentaire locale, extraction de texte minimale, chunking structure-aware, génération d'embeddings de chunks, recherche sémantique pgvector, réponse LLM avec citations de chunks, abstention contrôlée, migrations Alembic, documentation et tests de base.

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
- `POST /documents/{document_id}/embed` pour générer et stocker les embeddings des chunks;
- `POST /search` pour chercher les chunks les plus pertinents par similarité vectorielle;
- `POST /answer` pour générer une réponse avec citations à partir des chunks retrouvés, avec contexte délimité et durcissement prompt injection;
- un harness d'évaluation RAG minimal avec dataset JSONL, métriques simples et rapports locaux;
- `GET /documents/{document_id}/chunks` pour inspecter les chunks d'un document;
- `GET /documents` pour lister les documents;
- une configuration locale de dossier d'upload, dossier d'extraction, taille maximale et limites de chunking;
- une base PostgreSQL locale lancée avec Docker Compose;
- l'image PostgreSQL `pgvector/pgvector:pg16`;
- l'extension `vector` activée via Alembic;
- Alembic pour versionner le schéma local;
- le SDK OpenAI pour générer les embeddings et les réponses LLM;
- un frontend Next.js minimal;
- des tests pytest pour `/health`, les documents, l'upload, l'extraction, le chunking, les embeddings, la recherche sémantique et les réponses RAG.

Ce qui n'existe pas encore:

- OCR pour les PDF scannés;
- agentique, tool calling ou LangGraph;
- authentification, rôles ou isolation tenant;
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
- OpenAI SDK
- psycopg
- PostgreSQL
- pgvector
- Alembic
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

OPENAI_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_BATCH_SIZE=64

DEFAULT_SEARCH_TOP_K=5
MAX_SEARCH_TOP_K=20
MAX_SEARCH_QUERY_CHARS=1000

LLM_MODEL=gpt-4o-mini
ANSWER_CONTEXT_MAX_CHARS=6000
ANSWER_SOURCE_MAX_CHARS=1200
```

Ne commit jamais de vrais secrets dans `.env`. Le fichier `.env.example` sert uniquement de modèle local.
Les fichiers téléversés sont sauvegardés localement dans `UPLOAD_DIR`. Les textes extraits sont sauvegardés dans `EXTRACTED_TEXT_DIR`. Les fichiers générés dans `data/uploads/` et `data/extracted/` sont ignorés par Git.
`CHUNK_MAX_CHARS` et `CHUNK_OVERLAP_CHARS` contrôlent la taille des chunks créés depuis le texte extrait. L'overlap est surtout utilisé lorsque le backend doit couper un bloc trop long.
`OPENAI_API_KEY` est requis pour générer les embeddings de chunks, les embeddings de query utilisés par `POST /search`, et les réponses LLM de `POST /answer`. `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` et `EMBEDDING_BATCH_SIZE` contrôlent la génération des embeddings de chunks. La dimension actuelle doit rester `1536`, car la colonne PostgreSQL est typée `vector(1536)`.
`DEFAULT_SEARCH_TOP_K`, `MAX_SEARCH_TOP_K` et `MAX_SEARCH_QUERY_CHARS` contrôlent les limites de la recherche sémantique.
`LLM_MODEL` choisit le modèle chat utilisé par `POST /answer`. `ANSWER_CONTEXT_MAX_CHARS` limite le contexte total transmis au LLM, et `ANSWER_SOURCE_MAX_CHARS` limite l'extrait de chaque chunk cité. Le contexte RAG est borné par source avec des marqueurs `BEGIN/END SOURCE`; les textes de sources sont traités comme des données non fiables, jamais comme des instructions.

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
uv run uvicorn --app-dir src opsguard_api.main:app --reload
```

L'API est disponible par défaut sur:

```text
http://127.0.0.1:8000
```

Au démarrage local, l'API applique les migrations Alembic jusqu'à `head`. La première migration active l'extension PostgreSQL `vector`, crée les tables documentaires et ajoute `document_chunks.embedding vector(1536)`.

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
Pour appliquer explicitement les migrations:

```bash
uv run alembic upgrade head
```

## Lancer les évaluations RAG

Le dataset d'exemple vit dans `data/eval/rag_eval_cases.jsonl`. Remplace les
`document_id` et `expected_chunk_ids` par les IDs réellement présents dans ta base
locale avant de l'utiliser comme garde-fou de régression.

Dans `apps/api`:

```bash
PYTHONPATH=src uv run python -m opsguard_api.evals.run_rag_evals --cases data/eval/rag_eval_cases.jsonl
```

Le runner utilise le pipeline réel de retrieval et de réponse. Il requiert donc
`OPENAI_API_KEY` dans `.env` ou dans l'environnement shell, contrairement aux tests
pytest qui restent déterministes et mockent/fakent les appels externes.

Les rapports sont écrits dans:

```text
reports/evals/rag_eval_report.md
reports/evals/rag_eval_results.json
```

La commande retourne un code non nul si au moins un cas échoue, ce qui permet de
repérer rapidement une régression après un changement de chunking, embeddings,
prompt ou modèle.

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

### `POST /documents/{document_id}/embed`

Génère un embedding OpenAI pour chaque chunk déjà persisté, puis stocke les vecteurs dans `document_chunks.embedding` avec pgvector. Le document doit être `chunked`, `embedded` ou `embedding_failed`. Rappeler l'endpoint est idempotent: les chunks ne sont pas recréés et les embeddings existants sont remplacés.

Réponse exemple:

```json
{
  "document_id": 2,
  "status": "embedded",
  "embedding_model": "text-embedding-3-small",
  "embedding_dimensions": 1536,
  "embedded_chunk_count": 4,
  "message": "Document chunks embedded successfully."
}
```

L'API ne renvoie jamais les vecteurs complets. En cas de succès, le statut passe à `embedded`. En cas d'échec provider ou stockage après le démarrage du traitement, il passe à `embedding_failed`.

### `POST /search`

Génère un embedding pour la question utilisateur avec le même client d'embeddings que les chunks, puis cherche les chunks les plus proches dans PostgreSQL avec pgvector. Cet endpoint fait uniquement du retrieval: il ne génère pas de réponse finale et ne produit pas de citations rédigées.

Payload exemple:

```json
{
  "query": "Quel est le délai pour signaler un incident ?",
  "document_id": 2,
  "top_k": 5
}
```

`document_id` est optionnel. S'il est absent, la recherche peut retourner des chunks embedded issus de plusieurs documents. Les chunks sans embedding sont ignorés.

Réponse exemple:

```json
{
  "query": "Quel est le délai pour signaler un incident ?",
  "top_k": 5,
  "result_count": 1,
  "results": [
    {
      "document_id": 2,
      "document_title": "Incident Response Policy",
      "chunk_id": 12,
      "chunk_index": 3,
      "section_title": "Incident Reporting",
      "content": "Security incidents must be reported within 24 hours.",
      "similarity_score": 0.84
    }
  ]
}
```

La recherche utilise la distance cosine pgvector (`embedding <=> query_embedding`) et retourne `similarity_score = 1 - distance`. Plus le score est élevé, plus le chunk est proche de la query. Les embeddings complets ne sont jamais renvoyés par l'API.

### `POST /answer`

Réutilise la recherche sémantique existante pour récupérer les chunks pertinents, construit un contexte contrôlé, puis appelle un client LLM injectable pour produire une réponse JSON avec citations. L'endpoint ne fait pas d'agentique, de tool calling, de LangGraph ou de job en arrière-plan.

Le contexte envoyé au LLM est explicitement délimité:

- la liste complète est encadrée par `BEGIN/END RETRIEVED SOURCES`;
- chaque chunk est encadré par `BEGIN/END SOURCE`;
- le contenu textuel du chunk est encadré par `BEGIN/END SOURCE <id> CONTENT`;
- chaque source porte un champ `detected_prompt_injection_signals`.

Le prompt système rappelle que les sources sont des données non fiables. Les instructions présentes dans les chunks, par exemple ignorer les instructions précédentes, révéler le prompt système, exfiltrer des secrets ou appeler un outil, doivent être ignorées. La détection est heuristique et annotative: elle n'ajoute ni judge LLM ni second retrieval, et elle ne bloque pas automatiquement un chunk. Les secrets évidents de type clé API, token, mot de passe ou credential assigné sont redigés dans les extraits envoyés au LLM et dans les citations retournées.

Payload exemple:

```json
{
  "query": "Quel est le délai pour signaler un incident ?",
  "document_id": 2,
  "top_k": 5
}
```

Réponse exemple:

```json
{
  "query": "Quel est le délai pour signaler un incident ?",
  "answer": "Les incidents de sécurité doivent être signalés dans les 24 heures. [S1]",
  "is_answered": true,
  "citations": [
    {
      "source_id": "S1",
      "document_id": 2,
      "document_title": "Incident Response Policy",
      "chunk_id": 12,
      "chunk_index": 3,
      "section_title": "Incident Reporting",
      "excerpt": "Security incidents must be reported within 24 hours.",
      "similarity_score": 0.84
    }
  ],
  "retrieved_chunk_count": 1
}
```

Si aucun chunk n'est récupéré, si le LLM indique que les sources sont insuffisantes, ou si le LLM ne retourne pas de citations valides parmi les sources fournies, l'API force l'abstention:

```json
{
  "query": "Quel est le délai pour signaler un incident ?",
  "answer": "Je ne sais pas d'apres les sources disponibles.",
  "is_answered": false,
  "citations": [],
  "retrieved_chunk_count": 0
}
```

Les citations sont basées sur les chunks du contexte (`S1`, `S2`, etc.) et incluent seulement des métadonnées utiles et un extrait borné. Les embeddings complets ne sont jamais renvoyés.

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

1. Ajouter des évaluations retrieval/RAG.
2. Ajouter les premières tâches de revue et les contrôles de sécurité.
3. Ajouter l'authentification et l'isolation tenant avant tout usage multi-utilisateur.

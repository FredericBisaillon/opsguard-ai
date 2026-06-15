# OpsGuard AI

OpsGuard AI est une plateforme de revue documentaire IA sécurisée, construite progressivement comme projet portfolio backend/IA. Le but est de démontrer une architecture web maintenable, testable et orientée sécurité pour l'ingestion, la recherche et la revue de documents sensibles.

Le projet possède maintenant un premier bloc RAG backend et une Review Console frontend minimale: ingestion documentaire locale, extraction de texte minimale, chunking structure-aware, génération d'embeddings de chunks, recherche sémantique pgvector, réponse LLM avec citations de chunks, abstention contrôlée, tâches de revue métier manuelles, première suggestion de tâches via tool calling sécurisé, audit events pour les actions IA importantes, authentification minimale par API key, migrations Alembic, documentation et tests de base.

## État actuel

Ce qui existe aujourd'hui:

- un monorepo avec `apps/api` et `apps/web`;
- une API FastAPI avec `GET /health`;
- un modèle `Document` SQLAlchemy;
- un modèle `DocumentChunk` SQLAlchemy;
- un modèle `ReviewTask` SQLAlchemy pour représenter des points de revue liés à un document ou à un chunk;
- un modèle `AuditEvent` SQLAlchemy pour tracer les actions IA et les changements métier sensibles;
- des schemas Pydantic pour créer et lire des documents;
- `POST /documents` pour créer une entrée documentaire;
- `POST /documents/upload` pour téléverser un PDF, Markdown ou texte brut localement;
- `POST /documents/{document_id}/extract-text` pour extraire le texte d'un document uploadé;
- `POST /documents/{document_id}/chunk` pour découper le texte extrait en chunks;
- `POST /documents/{document_id}/embed` pour générer et stocker les embeddings des chunks;
- `POST /search` pour chercher les chunks les plus pertinents par similarité vectorielle;
- `POST /answer` pour générer une réponse avec citations à partir des chunks retrouvés, avec contexte délimité et durcissement prompt injection;
- `POST /review-tasks`, `GET /review-tasks`, `GET /review-tasks/{task_id}`, `PATCH /review-tasks/{task_id}` et `POST /review-tasks/{task_id}/dismiss` pour gérer des tâches de revue manuelles;
- `POST /ai/review-tasks/suggest` pour demander au LLM une proposition structurée de tâche à partir du contexte RAG, avec création optionnelle après validation backend stricte;
- `GET /audit-events` et `GET /audit-events/{event_id}` pour lire les traces d'audit structurées;
- une authentification minimale par header `X-API-Key` sur tous les endpoints applicatifs sauf `GET /health`;
- un harness d'évaluation RAG minimal avec dataset JSONL, métriques simples et rapports locaux;
- `GET /documents/{document_id}/chunks` pour inspecter les chunks d'un document;
- `GET /documents` pour lister les documents;
- une configuration locale de dossier d'upload, dossier d'extraction, taille maximale et limites de chunking;
- une base PostgreSQL locale lancée avec Docker Compose;
- l'image PostgreSQL `pgvector/pgvector:pg16`;
- l'extension `vector` activée via Alembic;
- Alembic pour versionner le schéma local;
- le SDK OpenAI pour générer les embeddings, les réponses LLM et les tool calls structurés;
- une Review Console Next.js minimale pour piloter le flow principal depuis le navigateur;
- des tests pytest pour `/health`, les documents, l'upload, l'extraction, le chunking, les embeddings, la recherche sémantique, les réponses RAG, les tâches de revue et le tool calling sécurisé.

Ce qui n'existe pas encore:

- OCR pour les PDF scannés;
- agentique autonome, multi-outils ou LangGraph;
- workflow d'approbation complet pour les tâches suggérées par IA;
- authentification complète avec utilisateurs, rôles ou isolation tenant;
- viewer PDF complet, dashboard analytique avancé ou intégration SIEM;
- authentification frontend complète;
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

REQUIRE_API_KEY=true
OPS_GUARD_API_KEY=replace-with-local-dev-api-key
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

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
`REQUIRE_API_KEY` vaut `true` par défaut. Quand il est activé, tous les endpoints sauf `GET /health` exigent le header `X-API-Key` avec la valeur de `OPS_GUARD_API_KEY`. Si la clé est absente, invalide ou non configurée en mode strict, l'API retourne `401` avec `{"detail": "Invalid or missing API key"}`.
`CORS_ALLOWED_ORIGINS` liste les origins navigateur autorisées à appeler l'API locale, notamment la Review Console Next.js sur `http://localhost:3000`.
`OPENAI_API_KEY` est requis pour générer les embeddings de chunks, les embeddings de query utilisés par `POST /search`, les réponses LLM de `POST /answer`, et les suggestions IA de `POST /ai/review-tasks/suggest`. `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` et `EMBEDDING_BATCH_SIZE` contrôlent la génération des embeddings de chunks. La dimension actuelle doit rester `1536`, car la colonne PostgreSQL est typée `vector(1536)`.
`DEFAULT_SEARCH_TOP_K`, `MAX_SEARCH_TOP_K` et `MAX_SEARCH_QUERY_CHARS` contrôlent les limites de la recherche sémantique.
`LLM_MODEL` choisit le modèle chat utilisé par `POST /answer` et par `POST /ai/review-tasks/suggest`. `ANSWER_CONTEXT_MAX_CHARS` limite le contexte total transmis au LLM, et `ANSWER_SOURCE_MAX_CHARS` limite l'extrait de chaque chunk cité. Le contexte RAG est borné par source avec des marqueurs `BEGIN/END SOURCE`; les textes de sources sont traités comme des données non fiables, jamais comme des instructions.

## Authentification API key

`GET /health` reste public pour les probes locales. Tous les autres endpoints exigent une clé API serveur simple:

```bash
curl -H "X-API-Key: $OPS_GUARD_API_KEY" http://127.0.0.1:8000/documents
```

Cette API key est un garde-fou minimal pour le backend portfolio. Elle ne remplace pas une authentification complète: il n'y a pas encore d'utilisateurs, de JWT, de rôles, de sessions, de tenants ou de workflow de rotation de clés.

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

Au démarrage local, l'API applique les migrations Alembic jusqu'à `head`. La première migration active l'extension PostgreSQL `vector`, crée les tables documentaires et ajoute `document_chunks.embedding vector(1536)`. La migration suivante crée `review_tasks` avec ses liens document/chunk et ses contraintes de valeurs contrôlées. La migration `0003_audit_events` crée `audit_events` avec `metadata JSONB`, des liens optionnels vers document/tâche, des index de lecture et des contraintes sur les valeurs contrôlées.

## Lancer le frontend

Dans `apps/web`:

```bash
cp .env.example .env.local
pnpm dev
```

`apps/web/.env.local` peut définir:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Le frontend est disponible par défaut sur:

```text
http://localhost:3000
```

La Review Console permet de configurer temporairement la clé API côté navigateur, lister et uploader des documents, lancer extraction/chunking/embeddings, poser une question RAG, demander une suggestion de review task, dismiss des tasks et lire les audit events récents.

La clé saisie dans la console est stockée dans `localStorage` uniquement pour le développement et la démo. Elle ne remplace pas une authentification production.

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

Sauf mention contraire, les endpoints ci-dessous exigent le header `X-API-Key` lorsque `REQUIRE_API_KEY=true`. `GET /health` est le seul endpoint public.

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

### `POST /ai/review-tasks/suggest`

Réutilise le retrieval RAG existant, appelle le LLM avec un seul outil structuré `create_review_task`, puis valide strictement les arguments côté backend. Le LLM ne modifie jamais directement la base: il produit seulement une proposition. Par défaut, l'endpoint retourne cette suggestion sans créer de tâche. Si `auto_create = true`, le backend crée une `ReviewTask` avec `source = ai_suggested` après validation.

Payload exemple:

```json
{
  "query": "Analyse ce document et crée une tâche si une politique d'incident semble incomplète.",
  "document_id": 2,
  "top_k": 5,
  "auto_create": false
}
```

Réponse exemple sans création:

```json
{
  "suggested": true,
  "created": false,
  "suggestion": {
    "document_id": 2,
    "chunk_id": 12,
    "title": "Clarify incident escalation timeline",
    "description": "The incident response policy does not define timing.",
    "severity": "medium",
    "evidence": "Escalation is required, but no timeline is stated.",
    "reason": "Reviewers need a concrete escalation deadline."
  },
  "review_task": null,
  "citations": [
    {
      "source_id": "S1",
      "document_id": 2,
      "document_title": "Incident Response Policy",
      "chunk_id": 12,
      "chunk_index": 3,
      "section_title": "Incident Escalation",
      "excerpt": "Escalation is required, but no timeline is stated.",
      "similarity_score": 0.82
    }
  ],
  "message": "Review task suggestion validated; no task was created.",
  "model": "gpt-4o-mini"
}
```

Garde-fous principaux:

- les sources sont présentées au LLM comme du contenu non fiable;
- le backend refuse un `document_id` différent de la requête;
- le backend refuse un `chunk_id` absent des chunks récupérés;
- le backend exige pour cette première version une preuve liée à un chunk;
- `title`, `description`, `severity`, `evidence` et `reason` sont revalidés par Pydantic;
- `source = ai_suggested` est imposé par le backend;
- les embeddings ne sont jamais renvoyés.

### `POST /review-tasks`

Crée une tâche de revue manuelle liée à un document, et optionnellement à un chunk précis. Cet endpoint ne fait aucun appel LLM et ne crée pas de tâche automatiquement.

Payload exemple:

```json
{
  "document_id": 2,
  "chunk_id": 12,
  "title": "Clause MFA potentiellement incomplète",
  "description": "Vérifier si la politique précise les exceptions et la fréquence de revue.",
  "severity": "high",
  "status": "open"
}
```

Valeurs acceptées:

- `severity`: `low`, `medium`, `high`, `critical`;
- `status`: `open`, `in_progress`, `resolved`, `dismissed`;
- `source`: `manual` ou `ai_suggested`, mais la création API actuelle force `manual`.

Validation métier:

- document inexistant: `404`;
- chunk inexistant: `404`;
- chunk appartenant à un autre document: `400`;
- titre ou description vide après trim: `422`;
- `severity` ou `status` invalide: `422`.

Réponse exemple:

```json
{
  "id": 1,
  "document_id": 2,
  "chunk_id": 12,
  "title": "Clause MFA potentiellement incomplète",
  "description": "Vérifier si la politique précise les exceptions et la fréquence de revue.",
  "severity": "high",
  "status": "open",
  "source": "manual",
  "created_at": "2026-06-14T12:00:00Z",
  "updated_at": "2026-06-14T12:00:00Z"
}
```

### `GET /review-tasks`

Liste les tâches de revue. Les filtres optionnels sont `document_id`, `status` et `severity`.

Exemple:

```text
GET /review-tasks?document_id=2&status=open&severity=high
```

### `GET /review-tasks/{task_id}`

Retourne une tâche de revue par identifiant.

### `PATCH /review-tasks/{task_id}`

Met à jour partiellement `title`, `description`, `severity` ou `status`. `description` peut être mise à `null`; `title`, `severity` et `status` ne peuvent pas être mis à `null`.

### `POST /review-tasks/{task_id}/dismiss`

Marque une tâche comme `dismissed`. Il n'y a pas de suppression physique dans ce bloc afin de préserver l'historique métier minimal.

### `GET /audit-events`

Liste les événements d'audit, du plus récent au plus ancien. L'endpoint est en lecture seule: les écritures d'audit sont faites par les services internes, jamais par un `POST` public.

Filtres optionnels:

- `event_type`;
- `document_id`;
- `review_task_id`;
- `status`;
- `source`;
- `limit`, entre 1 et 500, avec 100 par défaut.

Événements actuellement tracés:

- création manuelle d'une review task;
- dismiss d'une review task;
- suggestion IA validée;
- création de review task via `auto_create = true`;
- rejet d'un tool call invalide;
- absence de suggestion IA;
- détection de signaux de prompt injection dans les flows RAG ou AI review.

Exemple:

```text
GET /audit-events?document_id=2&event_type=ai_review_task_created
```

Réponse exemple:

```json
[
  {
    "id": 10,
    "event_type": "ai_review_task_created",
    "actor_type": "ai",
    "actor_id": null,
    "document_id": 2,
    "review_task_id": 7,
    "source": "ai",
    "status": "success",
    "summary": "AI-created review task 7 for document 2.",
    "metadata": {
      "model": "gpt-4o-mini",
      "top_k": 5,
      "chunk_ids": [12],
      "created_task_id": 7,
      "suggestion_chunk_id": 12
    },
    "created_at": "2026-06-15T12:00:00Z"
  }
]
```

Les métadonnées d'audit sont volontairement courtes. Le backend supprime les clés sensibles comme `embedding`, `api_key`, `token`, `secret`, `password`, `credential`, `prompt` ou `context_text`, tronque les chaînes longues et ne stocke pas les prompts complets, les embeddings, les clés API ou le contenu complet des documents.

### `GET /audit-events/{event_id}`

Retourne un événement d'audit par identifiant. Il n'existe pas encore de pagination complète, de dashboard ou de contrôle d'accès dédié; l'API key ne fournit pas d'identité utilisateur, donc `actor_id` reste généralement `null`.

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

1. Enrichir progressivement les évaluations retrieval/RAG.
2. Ajouter une UX ou un workflow léger d'approbation autour des tâches `ai_suggested`.
3. Remplacer l'API key minimale par une authentification utilisateur complète avec rôles et isolation tenant avant tout usage multi-utilisateur.

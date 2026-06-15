# Architecture actuelle

Ce document décrit l'architecture actuelle d'OpsGuard AI. Il reflète l'état réel du projet à ce stade: API FastAPI, upload local minimal, extraction de texte locale, chunking structure-aware, embeddings de chunks, recherche sémantique pgvector, réponses RAG avec citations, tâches de revue manuelles ou suggérées par IA, audit events pour les actions sensibles, validation Pydantic, persistance PostgreSQL/pgvector, migrations Alembic et frontend Next.js minimal.

OpsGuard AI ne fait pas encore d'OCR, d'agentique autonome, de LangGraph, de workflow d'approbation complet, d'authentification utilisateur complète ou de multi-tenant.

## 1. Vue d'ensemble

Le système est organisé en monorepo:

```text
apps/
  api/   Backend FastAPI
  web/   Frontend Next.js minimal
docs/    Documentation projet
```

Le backend expose actuellement une API HTTP simple:

- `GET /health`
- `POST /documents`
- `POST /documents/upload`
- `POST /documents/{document_id}/extract-text`
- `POST /documents/{document_id}/chunk`
- `POST /documents/{document_id}/embed`
- `POST /search`
- `POST /answer`
- `POST /ai/review-tasks/suggest`
- `POST /review-tasks`
- `GET /review-tasks`
- `GET /review-tasks/{task_id}`
- `PATCH /review-tasks/{task_id}`
- `POST /review-tasks/{task_id}/dismiss`
- `GET /audit-events`
- `GET /audit-events/{event_id}`
- `GET /documents/{document_id}/chunks`
- `GET /documents`

`GET /health` est public. Tous les autres endpoints sont protégés par une API key serveur minimale via le header `X-API-Key` lorsque `REQUIRE_API_KEY=true`.

La base de données locale est PostgreSQL dans Docker. L'image utilisée inclut pgvector, les embeddings de chunks sont stockés dans `document_chunks.embedding`, et `POST /search` utilise cette colonne pour le retrieval vectoriel. `POST /answer` réutilise ce retrieval, construit un contexte borné, puis appelle un client LLM injectable pour produire une réponse citée ou une abstention. `POST /ai/review-tasks/suggest` réutilise le même retrieval, demande au LLM un tool call structuré, valide les arguments côté backend, puis crée optionnellement une tâche `ai_suggested`. Les tâches de revue sont stockées dans `review_tasks`. Les traces structurées sont stockées dans `audit_events`.

## 2. Frontend actuel

Le frontend vit dans `apps/web`.

Technologies:

- Next.js
- TypeScript
- Tailwind
- pnpm

Son rôle actuel est minimal. Il sert de point de départ frontend pour le projet portfolio, mais il ne contient pas encore de dashboard documentaire, d'upload, d'écran d'authentification ou de workflow de revue.

## 3. Backend actuel

Le backend vit dans `apps/api`.

Technologies:

- FastAPI pour l'API HTTP;
- Pydantic pour les contrats API;
- pydantic-settings pour la configuration;
- SQLAlchemy pour l'accès relationnel;
- psycopg comme driver PostgreSQL;
- pypdf pour l'extraction de texte PDF sans OCR;
- pgvector pour le type vectoriel PostgreSQL et la recherche cosine;
- OpenAI SDK pour la génération d'embeddings, les réponses LLM et les tool calls structurés;
- Alembic pour les migrations;
- pytest, ruff et mypy pour la qualité.

L'application FastAPI est définie dans `opsguard_api.main`. Au démarrage local, son lifespan appelle `init_database()`, qui applique les migrations Alembic jusqu'à `head`.

## 3.1. Authentification API key

L'authentification actuelle est volontairement minimale. Le backend lit:

- `REQUIRE_API_KEY`, `true` par défaut;
- `OPS_GUARD_API_KEY`, la clé serveur attendue.

La dependency `opsguard_api.security.require_api_key` est appliquée au niveau des routers applicatifs dans `opsguard_api.main`. Elle lit le header `X-API-Key`, vérifie que la clé serveur est configurée en mode strict, puis compare les valeurs avec `secrets.compare_digest`.

En cas de clé absente, invalide ou non configurée, l'API retourne HTTP `401` avec:

```json
{"detail": "Invalid or missing API key"}
```

Cette couche protège les workflows sensibles sans introduire encore d'utilisateurs, de JWT, de rôles, de sessions ou de tenants. Elle ne fournit pas d'identité utilisateur: les `audit_events.actor_id` restent donc généralement `NULL`.

## 4. Validation avec Pydantic

Les schemas Pydantic sont définis dans `opsguard_api.schemas`.

`DocumentCreate` valide les données reçues par `POST /documents`:

- `title`: texte obligatoire entre 1 et 255 caractères;
- `source_type`: texte obligatoire entre 1 et 50 caractères;
- `source_path`: texte obligatoire.

`DocumentRead` définit la forme des réponses API:

- `id`;
- `title`;
- `source_type`;
- `source_path`;
- `status`;
- `created_at`;
- `updated_at`.

`DocumentRead` utilise `from_attributes=True`, ce qui permet à FastAPI/Pydantic de produire une réponse à partir d'un objet SQLAlchemy.

`DocumentExtractionRead` définit la réponse de l'extraction de texte:

- `document_id`;
- `status`;
- `extracted_text_path`;
- `character_count`;
- `message`.

`DocumentChunkingRead` définit la réponse du chunking:

- `document_id`;
- `status`;
- `chunk_count`;
- `chunk_max_chars`;
- `chunk_overlap_chars`;
- `message`.

`DocumentEmbeddingRead` définit la réponse de l'embedding:

- `document_id`;
- `status`;
- `embedding_model`;
- `embedding_dimensions`;
- `embedded_chunk_count`;
- `message`.

`DocumentChunkRead` expose un chunk persisté pour le debug et les tests:

- `id`;
- `document_id`;
- `chunk_index`;
- `content`;
- `character_count`;
- `section_title`;
- `start_char`;
- `end_char`;
- `created_at`.

`ReviewTaskCreate` définit l'entrée de `POST /review-tasks`:

- `document_id`: document obligatoire;
- `chunk_id`: chunk optionnel;
- `title`: texte obligatoire entre 1 et 255 caractères, trimé et non vide;
- `description`: texte optionnel, trimé et non vide si fourni;
- `severity`: `low`, `medium`, `high` ou `critical`, avec `medium` par défaut;
- `status`: `open`, `in_progress`, `resolved` ou `dismissed`, avec `open` par défaut.

`ReviewTaskUpdate` définit les champs modifiables par `PATCH /review-tasks/{task_id}`:

- `title`;
- `description`;
- `severity`;
- `status`.

`ReviewTaskRead` expose la tâche persistée avec `source`, `created_at` et `updated_at`. La création API manuelle force `source = manual`; le flow IA force `source = ai_suggested` uniquement après validation backend.

`ReviewTaskSuggestionRequest` définit l'entrée de `POST /ai/review-tasks/suggest`:

- `query`: demande utilisateur obligatoire, trimée et non vide;
- `document_id`: document obligatoire servant de filtre de retrieval;
- `top_k`: nombre optionnel de chunks à récupérer;
- `auto_create`: `false` par défaut. Si `true`, le backend crée la tâche après validation stricte.

`ReviewTaskSuggestion` décrit les arguments structurés attendus du tool call `create_review_task`:

- `document_id`;
- `chunk_id`;
- `title`;
- `description`;
- `severity`;
- `evidence`;
- `reason`.

Ce schema interdit les champs supplémentaires et revalide les longueurs, les enums et les chaînes vides. Pour cette première version, le service exige un `chunk_id` fourni et présent dans les sources récupérées.

`ReviewTaskSuggestionResponse` retourne l'état de la suggestion, l'éventuelle tâche créée, les citations utilisées, un message et le modèle LLM. Les citations n'exposent jamais les embeddings.

`SemanticSearchRequest` définit l'entrée de `POST /search`:

- `query`: texte obligatoire, trimé et non vide;
- `document_id`: filtre optionnel vers un document;
- `top_k`: nombre optionnel de résultats à retourner.

`SemanticSearchResponse` retourne la query, le `top_k` effectivement utilisé, le nombre de résultats et une liste de `SemanticSearchResult`.

Chaque `SemanticSearchResult` expose les métadonnées utiles du chunk retrouvé, dont `document_id`, `document_title`, `chunk_id`, `chunk_index`, `section_title`, `content` et `similarity_score`. Les embeddings complets ne sont pas exposés.

`AnswerRequest` définit l'entrée de `POST /answer`:

- `query`: texte obligatoire, trimé et non vide;
- `document_id`: filtre optionnel vers un document;
- `top_k`: nombre optionnel de chunks à récupérer via le search existant.

`AnswerResponse` retourne la query, le texte de réponse, `is_answered`, les citations retenues et `retrieved_chunk_count`. Chaque citation expose `source_id`, les métadonnées du chunk et un `excerpt` borné, jamais le vecteur d'embedding.

`AuditEventCreateInternal` est un schema interne utilisé par les services pour écrire une trace structurée. Il n'est pas exposé comme endpoint public de création. Il contrôle:

- `event_type`: type d'événement métier ou IA;
- `actor_type`: `system`, `human` ou `ai`;
- `actor_id`: optionnel tant qu'il n'y a pas d'identité utilisateur;
- `document_id` et `review_task_id`: liens optionnels;
- `source`: `manual`, `ai`, `api` ou `system`;
- `status`: `success`, `rejected`, `failed` ou `info`;
- `summary`: résumé court;
- `metadata`: JSON court, nettoyé par le service d'audit avant persistance.

`AuditEventRead` expose les événements via `GET /audit-events` et `GET /audit-events/{event_id}`. Le champ public s'appelle `metadata`, mais le modèle SQLAlchemy utilise l'attribut Python `event_metadata` parce que `metadata` est réservé par SQLAlchemy.

## 5. Routes vs services

Les routes sont responsables de la couche HTTP:

- recevoir la requête;
- valider l'API key via `require_api_key` pour tous les endpoints sauf `GET /health`;
- déclencher la validation Pydantic;
- obtenir une session DB via `Depends(get_db)`;
- appeler le service approprié;
- retourner un objet sérialisé par FastAPI.

Les services contiennent la logique applicative simple:

- créer un document;
- lister les documents;
- valider et sauvegarder un upload documentaire minimal;
- orchestrer l'extraction de texte et les changements de statut;
- orchestrer le chunking et la persistance des chunks;
- orchestrer la génération d'embeddings et leur stockage;
- orchestrer la recherche sémantique;
- orchestrer les réponses RAG avec contexte contrôlé, abstention et citations;
- orchestrer les suggestions IA de tâches via retrieval, tool calling structuré et validation backend;
- gérer les tâches de revue, dont la validation document/chunk;
- écrire et lire les audit events structurés;
- gérer les opérations SQLAlchemy nécessaires.

La lecture concrète des fichiers est isolée dans `opsguard_api.services.extraction`, afin de garder la logique `.md`, `.txt` et `.pdf` hors de la route HTTP.
La logique de découpage est isolée dans `opsguard_api.services.chunking`. Ce helper ne dépend pas de FastAPI ni de SQLAlchemy: il reçoit du texte et retourne des chunks typés avec section, offsets et taille.
La logique d'appel provider est isolée dans `opsguard_api.services.embeddings`. Les services documentaire et search dépendent d'un client d'embeddings testable, ce qui permet de mocker OpenAI dans les tests.
La logique de réponse est isolée dans `opsguard_api.services.answer`. Elle appelle `opsguard_api.services.retrieval`, qui réutilise `search_service.semantic_search` et transforme les chunks récupérés en sources `S1`, `S2`, etc. Le client LLM est isolé dans `opsguard_api.services.llm` et reste injectable pour les tests.
La logique de suggestion IA est isolée dans `opsguard_api.services.ai_review`. Elle appelle le retrieval existant, construit le prompt tool calling, valide les arguments proposés par le LLM, puis délègue la création optionnelle au service de tâches de revue.
La logique des tâches de revue est isolée dans `opsguard_api.services.review_tasks`. La route ne vérifie pas directement les relations document/chunk: elle valide le contrat HTTP, puis délègue au service. Le service expose une création manuelle et une création `ai_suggested`, toutes deux basées sur le même helper interne de validation document/chunk.
La logique d'audit est isolée dans `opsguard_api.services.audit_events`. Les routes d'audit ne lisent que les événements; les écritures sont déclenchées par les services métier ou IA. Le service nettoie défensivement les métadonnées avant stockage afin de ne pas conserver de secrets, embeddings, prompts complets ou contexte documentaire volumineux.

Cette séparation garde les routes minces et rend la logique métier plus facile à tester et à faire évoluer.

## 6. Modèles SQLAlchemy vs schemas Pydantic

Le modèle SQLAlchemy `Document` décrit la table persistée en base:

- nom de table: `documents`;
- colonnes: `id`, `title`, `source_type`, `source_path`, `status`, `created_at`, `updated_at`.
- relations vers `DocumentChunk` et `ReviewTask`.

Le modèle SQLAlchemy `DocumentChunk` décrit les chunks persistés:

- nom de table: `document_chunks`;
- colonnes: `id`, `document_id`, `chunk_index`, `content`, `character_count`, `section_title`, `start_char`, `end_char`, `embedding`, `created_at`;
- relation plusieurs-à-un vers `Document`;
- relation optionnelle inverse vers les `ReviewTask` qui ciblent ce chunk;
- contrainte unique `(document_id, chunk_index)`.

Le modèle SQLAlchemy `ReviewTask` décrit les tâches de revue métier:

- nom de table: `review_tasks`;
- colonnes: `id`, `document_id`, `chunk_id`, `title`, `description`, `severity`, `status`, `source`, `created_at`, `updated_at`;
- relation obligatoire vers `Document`;
- relation optionnelle vers `DocumentChunk`;
- `severity` contrôlé par `low`, `medium`, `high`, `critical`;
- `status` contrôlé par `open`, `in_progress`, `resolved`, `dismissed`;
- `source` contrôlé par `manual`, `ai_suggested`.

Si un document est supprimé, ses tâches sont supprimées avec lui. Si un chunk est supprimé ou recréé, le lien `chunk_id` de la tâche est mis à `NULL`, ce qui garde la tâche au niveau document.

Le modèle SQLAlchemy `AuditEvent` décrit les traces d'audit structurées:

- nom de table: `audit_events`;
- colonnes: `id`, `event_type`, `actor_type`, `actor_id`, `document_id`, `review_task_id`, `source`, `status`, `summary`, `metadata`, `created_at`;
- liens optionnels vers `documents` et `review_tasks` avec `ON DELETE SET NULL`;
- `event_type`, `actor_type`, `source` et `status` contrôlés par contraintes `CHECK`;
- `metadata` stocké en JSONB dans PostgreSQL.

Le lien `SET NULL` est volontaire: une trace d'audit doit survivre à la suppression d'un document ou d'une tâche, tout en évitant une référence cassée. Tant qu'il n'y a pas d'identité utilisateur, `actor_id` reste nullable.

Les schemas Pydantic décrivent les contrats de l'API:

- `DocumentCreate` pour l'entrée utilisateur;
- `DocumentRead` pour la sortie HTTP;
- `DocumentExtractionRead` pour l'extraction;
- `DocumentChunkingRead` et `DocumentChunkRead` pour le chunking;
- `DocumentEmbeddingRead` pour l'embedding des chunks;
- `ReviewTaskCreate`, `ReviewTaskUpdate` et `ReviewTaskRead` pour les tâches de revue;
- `ReviewTaskSuggestionRequest`, `ReviewTaskSuggestion`, `ReviewTaskSuggestionCitation` et `ReviewTaskSuggestionResponse` pour le tool calling sécurisé de suggestion de tâches;
- `AuditEventCreateInternal` et `AuditEventRead` pour l'écriture interne et la lecture des traces d'audit;
- `SemanticSearchRequest`, `SemanticSearchResult` et `SemanticSearchResponse` pour la recherche sémantique;
- `AnswerRequest`, `AnswerCitation` et `AnswerResponse` pour les réponses RAG citées.

Cette séparation évite de lier directement le contrat public de l'API au modèle de persistance. Elle permet aussi d'avoir des règles de validation différentes des contraintes SQL.

## 7. Connexion DB

La connexion à la base est centralisée dans `opsguard_api.db`.

Composants principaux:

- `Settings`: lit `DATABASE_URL` depuis `.env`;
- `Settings`: lit aussi `REQUIRE_API_KEY` et `OPS_GUARD_API_KEY` pour la protection HTTP minimale;
- `engine`: créé par SQLAlchemy avec `create_engine(...)`;
- `SessionLocal`: fabrique les sessions SQLAlchemy;
- `get_db()`: dépendance FastAPI qui fournit une session par requête;
- `init_database()`: applique les migrations Alembic au démarrage local.

Le driver utilisé par SQLAlchemy est psycopg, via une URL de ce format:

```text
postgresql+psycopg://opsguard:change-me-local-only@localhost:5432/opsguard_ai
```

PostgreSQL tourne localement avec Docker Compose. Le service utilise l'image:

```text
pgvector/pgvector:pg16
```

La migration initiale exécute:

```sql
CREATE EXTENSION IF NOT EXISTS vector
```

Elle crée aussi la colonne `document_chunks.embedding vector(1536)`. La migration suivante crée `review_tasks`, ses index `document_id` et `chunk_id`, ses foreign keys et ses contraintes `CHECK` sur `severity`, `status` et `source`. La migration `0003_audit_events` crée la table `audit_events`, ses index de filtrage, ses liens optionnels `SET NULL`, ses contraintes de valeurs contrôlées et son champ `metadata JSONB`. Les migrations peuvent être lancées explicitement avec `uv run alembic upgrade head` depuis `apps/api`.

## 8. Flow complet de `POST /documents`

Flux actuel:

```text
Client
-> POST /documents
-> FastAPI route create_document
-> validation Pydantic avec DocumentCreate
-> injection d'une session SQLAlchemy via get_db
-> appel du service documents_service.create_document
-> création d'un objet Document
-> db.add(document)
-> db.commit()
-> db.refresh(document)
-> retour de l'objet Document
-> sérialisation avec DocumentRead
-> réponse HTTP 201
```

Le `status` initial est défini à `uploaded`. Pour cette route historique, ce statut signifie seulement que l'entrée documentaire existe en base. Aucun fichier n'est téléversé par `POST /documents`.

## 9. Flow complet de `POST /documents/upload`

Flux actuel:

```text
Client
-> POST /documents/upload en multipart/form-data
-> FastAPI route upload_document
-> réception du champ file et du titre optionnel
-> injection d'une session SQLAlchemy via get_db
-> lecture de Settings via get_settings
-> appel du service documents_service.create_uploaded_document
-> validation extension + content-type
-> sauvegarde locale dans UPLOAD_DIR avec un nom serveur UUID
-> création d'un Document avec source_type = uploaded_file
-> db.add(document)
-> db.commit()
-> db.refresh(document)
-> sérialisation avec DocumentRead
-> réponse HTTP 201
```

Cette route accepte les PDF, Markdown et texte brut. Elle limite la taille via `MAX_UPLOAD_SIZE_MB`, refuse les fichiers vides, ne fait pas confiance au nom client pour le chemin final, et ne déclenche pas automatiquement extraction, chunking ou embedding.

## 10. Flow complet de `POST /documents/{document_id}/extract-text`

Flux actuel:

```text
Client
-> POST /documents/{document_id}/extract-text
-> FastAPI route extract_document_text
-> injection d'une session SQLAlchemy via get_db
-> lecture de Settings via get_settings
-> appel du service documents_service.extract_document_text
-> récupération du Document par id
-> validation du source_path déjà stocké en base
-> vérification que le fichier est dans UPLOAD_DIR
-> appel du helper services.extraction.extract_text
-> lecture UTF-8 pour .md/.txt ou extraction pypdf pour .pdf
-> sauvegarde du texte dans EXTRACTED_TEXT_DIR
-> mise à jour du status à text_extracted
-> sérialisation avec DocumentExtractionRead
-> réponse HTTP 200
```

En cas d'échec après récupération du document, le statut passe à `extraction_failed`. L'endpoint retourne `404` si le document ou son fichier source n'existe pas, et `400` si le type ou le contenu ne permet pas d'extraire du texte.

## 11. Flow complet de `POST /documents/{document_id}/chunk`

Flux actuel:

```text
Client
-> POST /documents/{document_id}/chunk
-> FastAPI route chunk_document
-> injection d'une session SQLAlchemy via get_db
-> lecture de Settings via get_settings
-> appel du service documents_service.chunk_document
-> récupération du Document par id
-> vérification du status text_extracted, chunked ou chunking_failed
-> résolution contrôlée de EXTRACTED_TEXT_DIR/document-{document_id}.txt
-> lecture du texte extrait
-> appel du helper services.chunking.chunk_text
-> suppression des anciens chunks du document
-> insertion des nouveaux DocumentChunk
-> mise à jour du status à chunked
-> sérialisation avec DocumentChunkingRead
-> réponse HTTP 200
```

Le chunking est idempotent: rappeler l'endpoint supprime les chunks existants du document avant de les recréer. En cas d'échec après récupération du document, le statut passe à `chunking_failed`.

Le chunker applique une stratégie structure-aware minimale:

- normalisation légère des sauts de ligne et espaces;
- détection de titres Markdown, titres numérotés simples et titres courts en majuscules;
- découpage par blocs logiques séparés par lignes vides;
- conservation du contexte de section dans le contenu du chunk;
- respect de `CHUNK_MAX_CHARS` autant que possible;
- overlap limité via `CHUNK_OVERLAP_CHARS` lorsque des blocs trop longs doivent être coupés.

## 12. Flow complet de `POST /documents/{document_id}/embed`

Flux actuel:

```text
Client
-> POST /documents/{document_id}/embed
-> FastAPI route embed_document
-> injection d'une session SQLAlchemy via get_db
-> lecture de Settings via get_settings
-> injection d'un client EmbeddingClient
-> appel du service documents_service.embed_document_chunks
-> récupération du Document par id
-> vérification du status chunked, embedded ou embedding_failed
-> récupération des DocumentChunk ordonnés par chunk_index
-> validation de la configuration embeddings
-> mise à jour du status à embedding
-> appel du client d'embeddings par batch
-> écriture de chaque vecteur dans DocumentChunk.embedding
-> mise à jour du status à embedded
-> sérialisation avec DocumentEmbeddingRead
-> réponse HTTP 200
```

L'endpoint est idempotent: rappeler `embed` ne recrée pas les chunks et n'insère pas de doublons. Les embeddings existants sont remplacés sur les lignes `document_chunks` existantes.

En cas d'absence de document, la route retourne `404`. En cas de document non chunked ou sans chunks, elle retourne une erreur HTTP propre sans appeler le provider. En cas d'échec provider ou stockage après le démarrage du traitement, le document passe à `embedding_failed`.

La réponse ne renvoie jamais les vecteurs complets, uniquement le nombre de chunks embedded, le modèle, la dimension et le statut.

## 13. Flow complet de `POST /search`

Flux actuel:

```text
Client
-> POST /search
-> validation Pydantic avec SemanticSearchRequest
-> FastAPI route semantic_search
-> injection d'une session SQLAlchemy via get_db
-> lecture de Settings via get_settings
-> injection d'un client EmbeddingClient
-> appel du service search_service.semantic_search
-> validation top_k, longueur de query et dimensions embedding
-> vérification optionnelle du document_id
-> retour vide si aucun chunk embedded n'existe dans le scope demandé
-> génération de l'embedding de query
-> requête SQLAlchemy sur DocumentChunk join Document
-> filtre DocumentChunk.embedding IS NOT NULL
-> filtre document_id si fourni
-> tri pgvector par distance cosine
-> LIMIT top_k
-> conversion distance en similarity_score
-> sérialisation avec SemanticSearchResponse
-> réponse HTTP 200
```

La recherche utilise l'opérateur pgvector de distance cosine, équivalent à:

```sql
ORDER BY document_chunks.embedding <=> :query_embedding
```

Le champ retourné est `similarity_score = 1 - distance`. Plus le score est élevé, plus le chunk est proche de la query. Une distance plus petite signifie aussi un meilleur résultat.

Cet endpoint ne fait pas de génération de réponse LLM. Il retourne uniquement les chunks pertinents et leurs métadonnées.

## 14. Flow complet de `POST /answer`

Flux actuel:

```text
Client
-> POST /answer
-> validation Pydantic avec AnswerRequest
-> FastAPI route answer_question
-> injection d'une session SQLAlchemy via get_db
-> lecture de Settings via get_settings
-> injection d'un client EmbeddingClient
-> injection d'un client LLMClient
-> appel du service answer_service.answer_question
-> appel du service retrieval.retrieve_answer_context
-> réutilisation de search_service.semantic_search
-> génération de l'embedding de query par le client d'embeddings
-> recherche pgvector des chunks les plus proches
-> construction de sources contrôlées S1, S2, etc.
-> redaction des secrets évidents dans les extraits de sources
-> détection heuristique de signaux de prompt injection dans les chunks
-> écriture d'un audit event si des signaux de prompt injection sont détectés
-> construction d'un prompt avec question + contexte borné et délimité
-> appel du LLM client
-> validation de la sortie JSON is_answered / answer / citations
-> validation que les citations demandées existent dans le contexte
-> sérialisation avec AnswerResponse
-> réponse HTTP 200
```

Le service de réponse ne duplique pas la logique de vector search. Toute récupération de chunks passe par `search_service.semantic_search`, via `services.retrieval`.

Le contexte envoyé au LLM est borné par:

- `ANSWER_CONTEXT_MAX_CHARS` pour le contexte total;
- `ANSWER_SOURCE_MAX_CHARS` pour l'extrait de chaque chunk.

Chaque source reçoit un identifiant local au contexte (`S1`, `S2`, etc.) et contient le titre du document, l'id du chunk, l'index du chunk, la section, le score de similarité, un champ `detected_prompt_injection_signals` et l'extrait. Les embeddings ne sont pas inclus dans le prompt et ne sont jamais renvoyés dans la réponse.

Le contexte est délimité à deux niveaux:

- `BEGIN/END RETRIEVED SOURCES` encadre toute la liste;
- `BEGIN/END SOURCE` et `BEGIN/END SOURCE <id> CONTENT` encadrent chaque source et son texte non fiable.

Le prompt système précise que les sources sont des données non fiables et que leurs instructions ne doivent jamais être suivies. La détection de prompt injection est volontairement simple et locale: elle cherche des motifs comme l'ignorance d'instructions précédentes, la prise de rôle, la révélation du prompt système, l'exfiltration de secrets ou l'appel à des outils externes. Les signaux sont transmis comme avertissements au LLM; ils ne déclenchent pas de judge LLM, ne refont pas de retrieval et ne changent pas la recherche pgvector.

Avant troncature, les extraits de sources passent aussi par une redaction déterministe des secrets évidents, par exemple les valeurs assignées à `api_key`, `secret`, `token`, `password` ou `credential`, ainsi que les clés OpenAI au format `sk-...`.

L'abstention est forcée côté service dans les cas suivants:

- aucun chunk embedded n'est récupéré;
- le LLM retourne `is_answered = false`;
- le LLM retourne une réponse vide;
- le LLM retourne une réponse sans citation;
- le LLM cite une source qui n'existe pas dans le contexte.

Dans ces cas, l'API retourne `is_answered = false`, la réponse d'abstention standard et une liste de citations vide.

## 15. Flow complet de `POST /review-tasks`

Flux actuel:

```text
Client
-> POST /review-tasks
-> validation Pydantic avec ReviewTaskCreate
-> FastAPI route create_review_task
-> injection d'une session SQLAlchemy via get_db
-> appel du service review_tasks_service.create_review_task
-> vérification que Document existe
-> si chunk_id est fourni, vérification que DocumentChunk existe
-> vérification que DocumentChunk.document_id correspond au document_id fourni
-> création d'un ReviewTask avec source = manual
-> db.add(task)
-> db.flush() pour obtenir task.id
-> écriture d'un audit event review_task_created
-> db.commit()
-> db.refresh(task)
-> sérialisation avec ReviewTaskRead
-> réponse HTTP 201
```

Le service retourne:

- `404` si le document n'existe pas;
- `404` si le chunk fourni n'existe pas;
- `400` si le chunk existe mais appartient à un autre document.

Les valeurs invalides de `severity` ou `status` sont rejetées par Pydantic avant l'appel du service. La table applique aussi des contraintes `CHECK` pour éviter qu'une écriture hors API stocke des valeurs inattendues.

La liste `GET /review-tasks` accepte les filtres optionnels `document_id`, `status` et `severity`. `PATCH /review-tasks/{task_id}` modifie seulement `title`, `description`, `severity` et `status`. `POST /review-tasks/{task_id}/dismiss` met `status = dismissed` sans suppression physique et écrit un audit event `review_task_dismissed`.

## 16. Flow complet de `POST /ai/review-tasks/suggest`

Flux actuel:

```text
Client
-> POST /ai/review-tasks/suggest
-> validation Pydantic avec ReviewTaskSuggestionRequest
-> FastAPI route suggest_review_task
-> injection DB, Settings, EmbeddingClient et LLMClient
-> appel du service ai_review.suggest_review_task
-> retrieval.retrieve_answer_context
-> search_service.semantic_search
-> construction des sources S1, S2, etc.
-> écriture d'un audit event si des signaux de prompt injection sont détectés
-> si aucun chunk n'est récupéré, audit event ai_review_no_suggestion
-> appel LLM avec l'outil create_review_task
-> parsing du tool call
-> si aucun tool call n'est retourné, audit event ai_review_no_suggestion
-> validation backend des arguments LLM
-> si le tool call est invalide, audit event ai_review_task_rejected
-> si le tool call est valide, audit event ai_review_task_suggested
-> si auto_create = false, retour de la suggestion validée
-> si auto_create = true, appel de review_tasks_service.create_ai_suggested_review_task
-> création d'un ReviewTask avec source = ai_suggested
-> écriture d'un audit event ai_review_task_created
-> sérialisation avec ReviewTaskSuggestionResponse
-> réponse HTTP 200
```

Le LLM ne reçoit aucun accès direct à SQLAlchemy ou PostgreSQL. Il peut seulement proposer des arguments structurés. Le backend conserve l'autorité:

- `document_id` doit correspondre à la requête;
- `chunk_id` doit être présent dans les sources récupérées;
- le chunk cité doit appartenir au document demandé;
- `severity` doit être une valeur contrôlée;
- `title`, `description`, `evidence` et `reason` sont bornés et trimés;
- `source = ai_suggested` est imposé par le service backend;
- les embeddings ne sont jamais renvoyés.

Si aucun chunk n'est récupéré, le LLM n'est pas appelé. Si le LLM ne fait aucun tool call, la réponse indique qu'aucune suggestion concrète n'est supportée. Si le tool call est invalide ou non vérifiable, l'API refuse la sortie du modèle et ne crée aucune tâche.

Le prompt rappelle que les sources sont du contenu non fiable. Les instructions contenues dans les documents, comme ignorer les règles précédentes, révéler les prompts ou exfiltrer des secrets, doivent être ignorées. Les sources servent uniquement de preuve.

Les audit events d'AI review stockent des métadonnées courtes comme le modèle, `top_k`, `auto_create`, les `chunk_ids`, l'erreur de validation ou l'id de la tâche créée. Ils ne stockent pas les prompts complets, les embeddings, les clés API ou le contenu complet des chunks.

## 17. Flow complet de `GET /audit-events`

Flux actuel:

```text
Client
-> GET /audit-events
-> FastAPI route list_audit_events
-> validation des filtres event_type, document_id, review_task_id, status, source, limit
-> injection d'une session SQLAlchemy via get_db
-> appel du service audit_events_service.list_audit_events
-> requête SQLAlchemy select(AuditEvent)
-> application des filtres optionnels
-> tri par created_at desc, puis id desc
-> LIMIT borné entre 1 et 500
-> sérialisation avec list[AuditEventRead]
-> réponse HTTP 200
```

`GET /audit-events/{event_id}` retourne un événement précis ou `404` s'il n'existe pas. Il n'y a volontairement pas de `POST /audit-events`: les écritures d'audit viennent des services internes.

Les événements actuellement tracés sont:

- `review_task_created`;
- `review_task_dismissed`;
- `ai_review_task_suggested`;
- `ai_review_task_created`;
- `ai_review_task_rejected`;
- `ai_review_no_suggestion`;
- `rag_prompt_injection_detected`.

Le service d'audit nettoie les métadonnées avant persistance: il supprime les clés sensibles comme `embedding`, `api_key`, `token`, `secret`, `password`, `credential`, `prompt` ou `context_text`, tronque les chaînes longues et borne la taille JSON finale. Cette couche est défensive; les call sites doivent quand même passer des métadonnées allowlistées et courtes.

## 18. Flow complet de `GET /documents/{document_id}/chunks`

Flux actuel:

```text
Client
-> GET /documents/{document_id}/chunks
-> FastAPI route list_document_chunks
-> injection d'une session SQLAlchemy via get_db
-> vérification que le Document existe
-> requête SQLAlchemy select(DocumentChunk)
-> tri par chunk_index
-> sérialisation avec list[DocumentChunkRead]
-> réponse HTTP 200
```

Cette route est volontairement simple. Elle aide à vérifier le résultat du chunking avant l'ajout d'un frontend complet. Elle n'expose pas la colonne `embedding`.

## 19. Flow complet de `GET /documents`

Flux actuel:

```text
Client
-> GET /documents
-> FastAPI route list_documents
-> injection d'une session SQLAlchemy via get_db
-> appel du service documents_service.list_documents
-> requête SQLAlchemy select(Document)
-> tri par created_at desc, puis id desc
-> retour d'une liste de Document
-> sérialisation avec list[DocumentRead]
-> réponse HTTP 200
```

Cette route expose les documents existants en base, sans pagination ni filtres pour l'instant.

## 20. Limites actuelles

Limites connues:

- les tests utilisent la base configurée par `DATABASE_URL`;
- il n'y a pas encore d'isolation de données par utilisateur ou tenant;
- il n'y a pas d'OCR pour les PDF scannés;
- les tâches suggérées par IA n'ont pas encore de workflow d'approbation dédié;
- le chunking reste heuristique et ne parse pas encore les tableaux ou structures PDF complexes;
- le RAG et la suggestion IA sont synchrones, sans agentique autonome, LangGraph ou queue;
- la dimension d'embedding est fixée à `1536` côté schéma PostgreSQL;
- la recherche vectorielle n'a pas encore d'index HNSW ou IVFFlat;
- l'endpoint d'embedding est synchrone et peut devenir lent sur de gros documents;
- il n'y a pas encore de workflow d'approbation, assignation, pagination complète des audit events ou observabilité avancée.

## 21. Prochaines étapes

Prochaines évolutions techniques recommandées:

1. Enrichir les évaluations retrieval/RAG et ajouter une CI plus complète.
2. Ajouter un workflow léger d'approbation et d'édition des tâches `ai_suggested`.
3. Ajouter auth, rôles et isolation tenant.
4. Ajouter un index vectoriel quand le volume de chunks le justifie.

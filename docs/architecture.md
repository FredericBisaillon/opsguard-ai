# Architecture actuelle

Ce document décrit l'architecture actuelle d'OpsGuard AI. Il reflète l'état réel du projet à ce stade: API FastAPI, upload local minimal, extraction de texte locale, chunking structure-aware, embeddings de chunks, recherche sémantique pgvector, réponses RAG avec citations, validation Pydantic, persistance PostgreSQL/pgvector, migrations Alembic et frontend Next.js minimal.

OpsGuard AI ne fait pas encore d'OCR, d'agentique, de tool calling, de LangGraph, d'authentification ou de multi-tenant.

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
- `GET /documents/{document_id}/chunks`
- `GET /documents`

La base de données locale est PostgreSQL dans Docker. L'image utilisée inclut pgvector, les embeddings de chunks sont stockés dans `document_chunks.embedding`, et `POST /search` utilise cette colonne pour le retrieval vectoriel. `POST /answer` réutilise ce retrieval, construit un contexte borné, puis appelle un client LLM injectable pour produire une réponse citée ou une abstention.

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
- OpenAI SDK pour la génération d'embeddings et les réponses LLM;
- Alembic pour les migrations;
- pytest, ruff et mypy pour la qualité.

L'application FastAPI est définie dans `opsguard_api.main`. Au démarrage local, son lifespan appelle `init_database()`, qui applique les migrations Alembic jusqu'à `head`.

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

## 5. Routes vs services

Les routes sont responsables de la couche HTTP:

- recevoir la requête;
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
- gérer les opérations SQLAlchemy nécessaires.

La lecture concrète des fichiers est isolée dans `opsguard_api.services.extraction`, afin de garder la logique `.md`, `.txt` et `.pdf` hors de la route HTTP.
La logique de découpage est isolée dans `opsguard_api.services.chunking`. Ce helper ne dépend pas de FastAPI ni de SQLAlchemy: il reçoit du texte et retourne des chunks typés avec section, offsets et taille.
La logique d'appel provider est isolée dans `opsguard_api.services.embeddings`. Les services documentaire et search dépendent d'un client d'embeddings testable, ce qui permet de mocker OpenAI dans les tests.
La logique de réponse est isolée dans `opsguard_api.services.answer`. Elle appelle `opsguard_api.services.retrieval`, qui réutilise `search_service.semantic_search` et transforme les chunks récupérés en sources `S1`, `S2`, etc. Le client LLM est isolé dans `opsguard_api.services.llm` et reste injectable pour les tests.

Cette séparation garde les routes minces et rend la logique métier plus facile à tester et à faire évoluer.

## 6. Modèles SQLAlchemy vs schemas Pydantic

Le modèle SQLAlchemy `Document` décrit la table persistée en base:

- nom de table: `documents`;
- colonnes: `id`, `title`, `source_type`, `source_path`, `status`, `created_at`, `updated_at`.

Le modèle SQLAlchemy `DocumentChunk` décrit les chunks persistés:

- nom de table: `document_chunks`;
- colonnes: `id`, `document_id`, `chunk_index`, `content`, `character_count`, `section_title`, `start_char`, `end_char`, `embedding`, `created_at`;
- relation plusieurs-à-un vers `Document`;
- contrainte unique `(document_id, chunk_index)`.

Les schemas Pydantic décrivent les contrats de l'API:

- `DocumentCreate` pour l'entrée utilisateur;
- `DocumentRead` pour la sortie HTTP;
- `DocumentExtractionRead` pour l'extraction;
- `DocumentChunkingRead` et `DocumentChunkRead` pour le chunking;
- `DocumentEmbeddingRead` pour l'embedding des chunks;
- `SemanticSearchRequest`, `SemanticSearchResult` et `SemanticSearchResponse` pour la recherche sémantique.
- `AnswerRequest`, `AnswerCitation` et `AnswerResponse` pour les réponses RAG citées.

Cette séparation évite de lier directement le contrat public de l'API au modèle de persistance. Elle permet aussi d'avoir des règles de validation différentes des contraintes SQL.

## 7. Connexion DB

La connexion à la base est centralisée dans `opsguard_api.db`.

Composants principaux:

- `Settings`: lit `DATABASE_URL` depuis `.env`;
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

Elle crée aussi la colonne `document_chunks.embedding vector(1536)`. Les migrations peuvent être lancées explicitement avec `uv run alembic upgrade head` depuis `apps/api`.

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

## 15. Flow complet de `GET /documents/{document_id}/chunks`

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

## 16. Flow complet de `GET /documents`

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

## 17. Limites actuelles

Limites connues:

- les tests utilisent la base configurée par `DATABASE_URL`;
- il n'y a pas encore d'isolation de données par utilisateur ou tenant;
- il n'y a pas d'OCR pour les PDF scannés;
- le chunking reste heuristique et ne parse pas encore les tableaux ou structures PDF complexes;
- le RAG actuel est synchrone, sans agentique, tool calling, LangGraph ou queue;
- la dimension d'embedding est fixée à `1536` côté schéma PostgreSQL;
- la recherche vectorielle n'a pas encore d'index HNSW ou IVFFlat;
- l'endpoint d'embedding est synchrone et peut devenir lent sur de gros documents;
- il n'y a pas encore de gestion d'erreurs avancée, pagination ou observabilité.

## 18. Prochaines étapes

Prochaines évolutions techniques recommandées:

1. Ajouter des évaluations retrieval/RAG et une CI plus complète.
2. Ajouter auth, rôles et isolation tenant.
3. Ajouter un index vectoriel quand le volume de chunks le justifie.

# Architecture actuelle

Ce document décrit l'architecture actuelle d'OpsGuard AI. Il reflète l'état réel du projet à ce stade: API FastAPI, upload local minimal, validation Pydantic, persistance PostgreSQL et frontend Next.js minimal.

OpsGuard AI ne fait pas encore de parsing de documents, d'embeddings, de recherche sémantique, de RAG, d'authentification ou de multi-tenant.

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
- `GET /documents`

La base de données locale est PostgreSQL dans Docker. L'image utilisée inclut pgvector afin de préparer les prochaines étapes liées aux embeddings, même si aucun embedding n'est encore stocké.

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
- pytest, ruff et mypy pour la qualité.

L'application FastAPI est définie dans `opsguard_api.main`. Au démarrage, son lifespan appelle `init_database()`, qui prépare temporairement la base locale.

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
- gérer les opérations SQLAlchemy nécessaires.

Cette séparation garde les routes minces et rend la logique métier plus facile à tester et à faire évoluer.

## 6. Modèles SQLAlchemy vs schemas Pydantic

Le modèle SQLAlchemy `Document` décrit la table persistée en base:

- nom de table: `documents`;
- colonnes: `id`, `title`, `source_type`, `source_path`, `status`, `created_at`, `updated_at`.

Les schemas Pydantic décrivent les contrats de l'API:

- `DocumentCreate` pour l'entrée utilisateur;
- `DocumentRead` pour la sortie HTTP.

Cette séparation évite de lier directement le contrat public de l'API au modèle de persistance. Elle permet aussi d'avoir des règles de validation différentes des contraintes SQL.

## 7. Connexion DB

La connexion à la base est centralisée dans `opsguard_api.db`.

Composants principaux:

- `Settings`: lit `DATABASE_URL` depuis `.env`;
- `engine`: créé par SQLAlchemy avec `create_engine(...)`;
- `SessionLocal`: fabrique les sessions SQLAlchemy;
- `get_db()`: dépendance FastAPI qui fournit une session par requête;
- `init_database()`: initialise temporairement la base au démarrage.

Le driver utilisé par SQLAlchemy est psycopg, via une URL de ce format:

```text
postgresql+psycopg://opsguard:change-me-local-only@localhost:5432/opsguard_ai
```

PostgreSQL tourne localement avec Docker Compose. Le service utilise l'image:

```text
pgvector/pgvector:pg16
```

Au démarrage, si le dialecte SQLAlchemy est PostgreSQL, l'API exécute:

```sql
CREATE EXTENSION IF NOT EXISTS vector
```

Cela prépare la base pour les futurs embeddings, sans ajouter encore de logique vectorielle dans l'application.

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

Cette route accepte seulement les PDF et Markdown. Elle limite la taille via `MAX_UPLOAD_SIZE_MB`, refuse les fichiers vides, ne fait pas confiance au nom client pour le chemin final, et ne déclenche pas encore de parsing, chunking ou embedding.

## 10. Flow complet de `GET /documents`

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

## 11. Limites actuelles

Limites connues:

- `create_all()` est utilisé temporairement au démarrage;
- il n'y a pas encore de migrations Alembic;
- les tests utilisent la base configurée par `DATABASE_URL`;
- il n'y a pas encore d'isolation de données par utilisateur ou tenant;
- il n'y a pas de parsing documentaire;
- il n'y a pas de chunks, embeddings ou recherche vectorielle;
- il n'y a pas de couche IA;
- il n'y a pas encore de gestion d'erreurs avancée, pagination ou observabilité.

## 12. Prochaines étapes

Prochaines évolutions techniques recommandées:

1. Introduire Alembic avant de complexifier le schéma.
2. Ajouter l'extraction de texte.
3. Introduire une table de chunks.
4. Générer et stocker des embeddings avec pgvector.
5. Construire une recherche sémantique.
6. Ajouter des réponses avec citations.
7. Ajouter auth, rôles et isolation tenant.
8. Ajouter des évaluations et une CI plus complète.

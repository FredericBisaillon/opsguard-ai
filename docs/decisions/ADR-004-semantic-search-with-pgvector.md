# ADR-004: Semantic search with pgvector

## Statut

Accepté.

## Contexte

OpsGuard AI possède déjà des documents découpés en chunks et des embeddings stockés dans PostgreSQL avec pgvector. L'étape suivante consiste à récupérer les chunks les plus pertinents pour une question utilisateur.

Ce bloc couvre uniquement:

```text
question utilisateur -> embedding de query -> recherche vectorielle pgvector -> chunks pertinents
```

Il ne couvre pas encore la génération de réponse finale, les citations rédigées, le chat, l'agentique, l'authentification ou les jobs en arrière-plan.

## Décision

Nous ajoutons un endpoint:

```text
POST /search
```

Le payload contient une `query`, un `document_id` optionnel et un `top_k` optionnel. Si `document_id` est absent, la recherche peut retourner des chunks embedded de plusieurs documents.

La query est embedded avec le même `EmbeddingClient` que les chunks. Le service de search ne connaît donc pas OpenAI directement: il dépend de l'abstraction `EmbeddingClient`, ce qui permet d'utiliser un fake déterministe dans les tests.

La recherche utilise la distance cosine pgvector sur `document_chunks.embedding`:

```sql
ORDER BY embedding <=> query_embedding
```

Les chunks sans embedding sont ignorés. La réponse ne retourne jamais les embeddings complets.

## Score retourné

pgvector retourne une distance: plus elle est petite, plus le vecteur est proche.

L'API expose plutôt:

```text
similarity_score = 1 - distance
```

Plus `similarity_score` est élevé, plus le chunk est pertinent pour la query. Ce choix rend la réponse plus naturelle pour les consommateurs de l'API, tout en gardant la formule documentée.

## Pourquoi `POST /search`

La recherche n'est pas strictement attachée à un seul document. Le filtre `document_id` est optionnel, et une recherche globale sur tous les documents embedded est valide. `POST /search` exprime donc mieux la brique retrieval que `POST /documents/search`.

## Pourquoi pas encore d'index vectoriel

Le volume actuel est local et portfolio. Une requête `ORDER BY embedding <=> query_embedding LIMIT top_k` est suffisante pour valider le comportement et garder la migration simple.

Un index HNSW ou IVFFlat deviendra pertinent lorsque le nombre de chunks augmentera et que la latence de recherche devra être optimisée.

## Trade-offs

Avantages:

- endpoint retrieval clair et isolé;
- pas de génération LLM hors scope;
- réutilisation du client d'embeddings existant;
- tests sans appel OpenAI réel;
- filtre optionnel par document;
- pas de fuite des vecteurs dans les réponses API.

Inconvénients:

- pas encore d'index vectoriel;
- pas de seuil de similarité minimal;
- pas de versioning du modèle d'embedding par chunk;
- la qualité dépend du chunking et des embeddings déjà stockés;
- pas encore d'évaluation retrieval.

## Améliorations futures

Évolutions possibles:

- ajouter un index HNSW ou IVFFlat;
- ajouter `min_similarity`;
- stocker `embedding_model`, `embedding_dimensions` et `embedded_at` par chunk;
- ajouter des évaluations retrieval;
- construire une réponse finale avec citations à partir des chunks retrouvés;
- ajouter auth, rôles et isolation tenant avant une recherche multi-utilisateur.

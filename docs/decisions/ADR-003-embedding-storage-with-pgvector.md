# ADR-003: Embedding storage with pgvector

## Statut

Accepté.

Note de suivi: les blocs retrieval et réponse citée ont ensuite été ajoutés dans `ADR-004` et `ADR-005`. Le contexte ci-dessous décrit la décision au moment où seuls les embeddings étaient introduits.

## Contexte

OpsGuard AI doit transformer les chunks documentaires en vecteurs afin de préparer la recherche sémantique et, plus tard, les réponses avec citations.

À ce stade, le projet ne doit pas encore ajouter de retrieval, de RAG, de génération LLM, d'agentique, d'authentification ou de queue. Le bloc actuel couvre uniquement:

```text
chunks texte -> embeddings -> stockage PostgreSQL/pgvector
```

## Décision

Nous stockons un embedding directement sur chaque ligne `document_chunks`, dans une colonne PostgreSQL:

```sql
embedding vector(1536)
```

Le modèle par défaut est `text-embedding-3-small`, appelé via le SDK OpenAI derrière un client applicatif testable. La route publique est:

```text
POST /documents/{document_id}/embed
```

Le document doit déjà être chunked. En succès, son statut passe à `embedded`. En échec provider ou stockage après le début du traitement, son statut passe à `embedding_failed`.

Le schéma est maintenant versionné avec Alembic. La migration initiale active l'extension `vector`, crée les tables si nécessaire et ajoute la colonne `embedding` de manière compatible avec la base locale précédemment créée par `create_all()`.

## Pourquoi PostgreSQL avec pgvector

PostgreSQL est déjà la base relationnelle du projet. Utiliser pgvector permet de garder les documents, chunks, statuts et vecteurs dans le même système de persistance pendant cette phase portfolio.

Ce choix réduit le nombre de composants opérationnels, garde les tests locaux simples et prépare une recherche vectorielle future sans introduire tout de suite un moteur spécialisé.

## Pourquoi un modèle d'embedding externe

Un modèle d'embedding externe évite de gérer l'inférence locale, le packaging GPU/CPU et la compatibilité des modèles. OpenAI fournit un endpoint stable, simple à appeler depuis Python et adapté à une première version backend.

Le code ne dépend pas d'OpenAI partout: la logique provider est isolée dans `services/embeddings.py`, derrière un client remplaçable.

## Pourquoi embedder les chunks

Embedder le document complet diluerait les passages utiles et rendrait les citations futures difficiles. Les chunks sont les unités de retrieval naturelles: ils sont plus courts, ordonnés, liés au document d'origine et peuvent conserver un contexte de section.

Le stockage sur `DocumentChunk` garde une relation directe entre texte, métadonnées de chunking et vecteur.

## Pourquoi pas encore le retrieval

Le retrieval ajoute de nouvelles décisions: métrique de distance, index HNSW ou IVFFlat, seuils, top-k, ranking, citations et évaluations. Les ajouter maintenant mélangerait trop de sujets.

Ce bloc valide d'abord que les embeddings sont générés, stockés et rejouables proprement.

## Pourquoi les tests mockent le provider

Les tests ne doivent pas appeler OpenAI parce que cela introduirait:

- un coût variable;
- une dépendance réseau;
- une dépendance à une clé secrète;
- des erreurs intermittentes;
- un risque d'exposer ou de mal gérer la configuration.

Les tests utilisent donc un faux client d'embeddings qui retourne des vecteurs déterministes de la bonne dimension.

## Idempotence

Rappeler `POST /documents/{document_id}/embed` ne recrée pas les chunks. Le service recharge les chunks existants et remplace leur colonne `embedding`.

Cette stratégie évite les doublons, respecte la contrainte unique `(document_id, chunk_index)` et permet de régénérer les vecteurs après une erreur provider ou un changement contrôlé de modèle.

## Trade-offs

Avantages:

- architecture simple et lisible;
- pas de base vectorielle séparée;
- intégration naturelle avec les chunks existants;
- client OpenAI isolé et testable;
- réponse API courte sans fuite des vecteurs;
- migrations Alembic au lieu de `create_all()`.

Inconvénients:

- la dimension `1536` est inscrite dans le schéma;
- pas encore d'index vectoriel;
- pas encore de versioning des embeddings par modèle;
- endpoint synchrone, donc moins adapté aux gros documents;
- coût provider à chaque re-embedding.

## Limites actuelles

- `EMBEDDING_DIMENSIONS` doit rester `1536` tant que le schéma est `vector(1536)`;
- les embeddings ne sont pas exposés par l'API;
- aucun endpoint de recherche vectorielle n'existe encore;
- aucun index HNSW/IVFFlat n'est créé;
- aucun mécanisme de retry automatique ou background job n'est présent;
- aucun audit d'usage provider n'est encore stocké.

## Améliorations futures

Évolutions possibles:

- ajouter une recherche sémantique avec top-k;
- ajouter un index vectoriel quand le volume le justifie;
- stocker `embedding_model`, `embedding_dimensions` et un hash de contenu par chunk;
- invalider les embeddings lors d'un re-chunking;
- ajouter une queue pour traiter les gros documents;
- ajouter des évaluations retrieval;
- construire les réponses avec citations.

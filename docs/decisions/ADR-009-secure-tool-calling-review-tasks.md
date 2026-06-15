# ADR-009: Secure tool calling for AI-suggested review tasks

## Statut

Accepté.

## Contexte

OpsGuard AI sait déjà ingérer des documents, extraire leur texte, créer des chunks, générer des embeddings, faire du semantic search, produire des réponses RAG avec citations et gérer des `review_tasks`.

Le prochain incrément utile est de permettre au LLM de transformer un constat supporté par les sources RAG en proposition de tâche de revue. Ce bloc doit rester limité:

- pas d'agent autonome;
- pas de LangGraph;
- pas de multi-outils;
- pas d'action destructive;
- pas de workflow complexe d'approbation;
- pas d'accès direct du LLM à la base de données.

## Décision

Nous ajoutons:

```text
POST /ai/review-tasks/suggest
```

L'endpoint reçoit une requête utilisateur, un `document_id`, un `top_k` optionnel et `auto_create`.

Le flow est:

```text
route
-> service ai_review
-> retrieval RAG existant
-> LLM avec l'outil create_review_task
-> validation backend stricte
-> création optionnelle via review_tasks_service
-> réponse avec suggestion, tâche éventuelle et citations
```

Par défaut, `auto_create = false`: l'API retourne seulement une suggestion validée. Si `auto_create = true`, le backend crée une `ReviewTask` avec `source = ai_suggested`.

## Outil

Un seul outil est exposé au LLM:

```text
create_review_task
```

Arguments attendus:

- `document_id`;
- `chunk_id`;
- `title`;
- `description`;
- `severity`;
- `evidence`;
- `reason`.

Le tool schema aide le modèle à produire une sortie structurée, mais il ne remplace pas la validation backend.

## Garde-fous

Le LLM ne modifie jamais directement PostgreSQL. Il produit seulement des arguments structurés.

Le backend vérifie:

- le `document_id` proposé correspond à la requête;
- le `chunk_id` proposé fait partie des chunks récupérés;
- le chunk appartient au document demandé;
- `title`, `description`, `evidence` et `reason` respectent les limites de longueur et ne sont pas vides;
- `severity` est `low`, `medium`, `high` ou `critical`;
- la création passe par le service `review_tasks`;
- `source = ai_suggested` est imposé côté backend.

Pour cette première version, une suggestion IA doit citer un chunk précis. Les tâches IA au niveau document complet pourront être ajoutées plus tard si le modèle de preuve devient plus explicite.

## Prompt injection

Le prompt rappelle que les sources RAG sont du contenu non fiable. Les instructions présentes dans les documents ne doivent pas être suivies. Les chunks servent uniquement de preuve.

Le retrieval existant continue de:

- délimiter les sources;
- détecter des signaux de prompt injection;
- rediger des secrets évidents;
- borner la taille des extraits.

## Trade-offs

Avantages:

- démonstration claire de tool calling sécurisé;
- séparation `route -> ai_review -> retrieval -> llm -> review_tasks -> DB`;
- backend autoritaire pour les écritures;
- compatible avec les tests déterministes via fake LLM;
- aucune migration nécessaire, car `ai_suggested` existe déjà.

Inconvénients:

- `evidence` et `reason` ne sont pas persistés séparément dans `review_tasks`;
- le flow reste synchrone;
- pas encore d'écran d'approbation ou d'édition;
- pas encore d'audit log complet des propositions refusées.

## Améliorations futures

Évolutions possibles:

- ajouter une UI pour accepter, éditer ou rejeter les suggestions;
- persister l'evidence et le reason dans une table dédiée;
- ajouter des évaluations spécifiques aux suggestions de tâches;
- ajouter un audit log lorsque l'authentification existera;
- introduire une agentique légère seulement après validation des workflows et garde-fous.

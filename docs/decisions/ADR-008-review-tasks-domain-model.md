# ADR-008: Review tasks domain model

## Statut

Accepté.

## Contexte

OpsGuard AI sait déjà ingérer des documents, extraire du texte, créer des chunks, stocker des embeddings, faire une recherche sémantique et générer des réponses RAG avec citations.

Avant d'ajouter du tool calling ou une couche agentique légère, le système a besoin d'une ressource métier explicite sur laquelle il pourra agir plus tard. Une réponse RAG citée aide l'utilisateur à comprendre un document, mais elle ne représente pas encore un travail de revue persisté.

Ce bloc ne doit pas introduire:

- agentique;
- tool calling;
- LangGraph;
- création automatique de tâches par LLM;
- analyse automatique de conformité;
- workflow d'approbation;
- notifications;
- assignation avancée;
- audit log complet.

## Décision

Nous ajoutons une table:

```text
review_tasks
```

Une `ReviewTask` représente un point de revue lié obligatoirement à un document et optionnellement à un chunk précis.

Champs principaux:

- `id`;
- `document_id`;
- `chunk_id`;
- `title`;
- `description`;
- `severity`;
- `status`;
- `source`;
- `created_at`;
- `updated_at`.

`document_id` est obligatoire parce qu'une tâche de revue doit toujours appartenir à un document métier.

`chunk_id` est optionnel parce qu'une tâche peut viser:

- tout le document, par exemple une date de révision manquante;
- un passage précis, par exemple une clause MFA incomplète.

## Valeurs contrôlées

`severity` accepte:

- `low`;
- `medium`;
- `high`;
- `critical`.

`status` accepte:

- `open`;
- `in_progress`;
- `resolved`;
- `dismissed`.

`source` accepte:

- `manual`;
- `ai_suggested`.

Pour ce bloc, les endpoints créent uniquement des tâches `manual`. La valeur `ai_suggested` prépare le terrain pour une future proposition ou création de tâches via tool calling, mais elle n'est pas utilisée automatiquement.

## API

Endpoints ajoutés:

```text
POST /review-tasks
GET /review-tasks
GET /review-tasks/{task_id}
PATCH /review-tasks/{task_id}
POST /review-tasks/{task_id}/dismiss
```

La suppression physique n'est pas exposée. `dismiss` est préféré pour conserver un minimum de trace métier sans introduire un audit log complet.

## Validation

La route reçoit la requête et déclenche la validation Pydantic. Le service `review_tasks` contient la logique métier:

- vérifier que le document existe;
- vérifier que le chunk existe si `chunk_id` est fourni;
- refuser un chunk qui appartient à un autre document;
- forcer `source = manual` à la création;
- persister la tâche via SQLAlchemy.

Les schemas Pydantic contrôlent les valeurs d'enum, les IDs positifs, les titres non vides et les longueurs de titre/description. La table ajoute aussi des contraintes `CHECK` sur `severity`, `status` et `source`.

## Relations et suppressions

Un `Document` possède plusieurs `ReviewTask`.

Un `DocumentChunk` peut avoir plusieurs `ReviewTask`.

Si un document est supprimé, ses tâches sont supprimées avec lui via `ON DELETE CASCADE`. Ce comportement reste simple et cohérent avec les chunks du document.

Si un chunk est supprimé, `review_tasks.chunk_id` passe à `NULL` via `ON DELETE SET NULL`. Cela préserve la tâche au niveau document quand les chunks sont régénérés.

## Trade-offs

Avantages:

- ressource métier claire avant l'automatisation;
- séparation route -> service -> DB;
- validation applicative et contraintes DB;
- compatible avec un futur tool calling sans l'introduire maintenant;
- pas d'appel OpenAI ni d'agentique dans ce bloc.

Inconvénients:

- pas encore de workflow complet de revue;
- pas de pagination;
- pas d'assignation ou de propriétaires;
- pas d'audit log détaillé;
- les tâches liées à un chunk peuvent perdre leur `chunk_id` si le document est rechunké.

## Améliorations futures

Évolutions possibles:

- ajouter pagination et tri avancé;
- ajouter assignation simple après l'authentification;
- ajouter un audit log quand les workflows deviennent plus riches;
- permettre au LLM de suggérer des tâches avec `source = ai_suggested`;
- exposer un outil contrôlé qui crée ou met à jour des `review_tasks`;
- relier les tâches aux citations RAG utilisées pour les proposer.

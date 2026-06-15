# ADR-010: AI audit events and action traceability

## Statut

Accepté.

## Contexte

OpsGuard AI sait maintenant ingérer des documents, extraire leur texte, créer des chunks, stocker des embeddings, faire du semantic search, générer des réponses RAG avec citations, créer des `review_tasks` et demander au LLM une suggestion de tâche via tool calling sécurisé.

Le système commence donc à avoir des actions IA importantes:

- une suggestion de tâche peut être proposée par le LLM;
- une tâche peut être créée avec `source = ai_suggested`;
- un tool call invalide peut être refusé;
- le retrieval peut détecter des signaux de prompt injection;
- une absence de suggestion peut être une information utile.

Sans trace structurée, il est difficile d'expliquer après coup pourquoi le backend a créé, refusé ou ignoré une action IA.

## Décision

Nous ajoutons une table:

```text
audit_events
```

Champs principaux:

- `id`;
- `event_type`;
- `actor_type`;
- `actor_id`;
- `document_id`;
- `review_task_id`;
- `source`;
- `status`;
- `summary`;
- `metadata`;
- `created_at`.

`metadata` est stocké en JSONB côté PostgreSQL. Côté SQLAlchemy, l'attribut Python s'appelle `event_metadata`, car `metadata` est réservé par le système declarative de SQLAlchemy.

## Événements tracés

Pour cette première version, nous traçons:

- `review_task_created`;
- `review_task_dismissed`;
- `ai_review_task_suggested`;
- `ai_review_task_created`;
- `ai_review_task_rejected`;
- `ai_review_no_suggestion`;
- `rag_prompt_injection_detected`.

Les écritures sont faites par les services internes:

```text
route -> service métier ou IA -> audit_events_service -> DB
```

Il n'y a pas de endpoint public `POST /audit-events`.

## Lecture API

Endpoints ajoutés:

```text
GET /audit-events
GET /audit-events/{event_id}
```

La liste accepte des filtres simples:

- `event_type`;
- `document_id`;
- `review_task_id`;
- `status`;
- `source`;
- `limit`.

## Garde-fous de données

L'audit log doit être utile sans devenir un dépôt de secrets ou de prompts.

Nous ne stockons pas:

- embeddings;
- clés API;
- tokens;
- secrets;
- mots de passe;
- variables d'environnement;
- prompts complets;
- contexte RAG complet;
- contenu complet des documents.

Les métadonnées privilégient:

- IDs de documents, chunks et tâches;
- modèle utilisé;
- `top_k`;
- `auto_create`;
- noms de signaux de prompt injection;
- erreur de validation courte;
- id de tâche créée.

Le service d'audit applique une sanitation défensive: suppression de clés sensibles, troncature des chaînes longues, borne sur les listes/dicts et limite de taille JSON finale.

## Relations et suppressions

`audit_events.document_id` et `audit_events.review_task_id` sont optionnels.

Les foreign keys utilisent `ON DELETE SET NULL`. Une trace doit survivre à la suppression d'un document ou d'une tâche, mais la base ne doit pas garder de référence cassée.

## Limites actuelles

Ce bloc ne remplace pas une vraie couche d'audit production:

- pas encore d'authentification;
- `actor_id` reste généralement `NULL`;
- pas de rôles ou permissions;
- pas de dashboard frontend;
- pas de SIEM;
- pas de politique de rétention;
- pagination limitée à un simple `limit`.

Ces limites sont acceptées pour garder ce bloc centré sur la traçabilité IA et les workflows déjà existants.

## Trade-offs

Avantages:

- trace structurée des succès, refus et absences de suggestion;
- meilleure explicabilité des actions IA;
- démonstration claire d'un réflexe sécurité backend;
- endpoints de lecture simples;
- pas de nouveau workflow complexe;
- tests déterministes avec fake LLM et fake embeddings.

Inconvénients:

- l'audit log n'a pas encore d'acteur utilisateur réel;
- les métadonnées sont volontairement minimales;
- il n'y a pas encore de pagination robuste;
- certaines actions non IA, comme `review_task_updated`, ne sont pas encore tracées.

## Améliorations futures

Évolutions possibles:

- ajouter `actor_id` réel après l'authentification;
- ajouter rôles, tenants et permission checks;
- tracer les mises à jour de tâches avec diff minimal;
- ajouter pagination cursor-based;
- ajouter export ou intégration SIEM;
- ajouter un écran d'audit dans le frontend;
- définir une politique de rétention et de masquage plus complète.

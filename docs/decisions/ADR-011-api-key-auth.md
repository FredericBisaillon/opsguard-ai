# ADR-011: Minimal API key authentication

## Statut

Accepté.

## Contexte

OpsGuard AI expose maintenant des endpoints sensibles:

- ingestion et upload de documents;
- extraction de texte;
- chunking;
- génération d'embeddings;
- recherche sémantique;
- réponse RAG avec appel LLM;
- suggestion de tâches via tool calling;
- création, modification et dismissal de `review_tasks`;
- lecture des `audit_events`.

Même en phase portfolio, ces endpoints ne doivent pas rester publics par défaut. Le projet n'est toutefois pas encore prêt pour une authentification complète avec utilisateurs, mots de passe, JWT, OAuth, RBAC ou multi-tenant.

## Décision

Nous ajoutons une protection minimale par API key serveur.

Configuration:

```env
REQUIRE_API_KEY=true
OPS_GUARD_API_KEY=replace-with-local-dev-api-key
```

Les clients doivent envoyer:

```text
X-API-Key: <configured key>
```

`GET /health` reste public. Tous les autres routers applicatifs sont protégés par la dependency FastAPI:

```text
opsguard_api.security.require_api_key
```

Cette dependency:

- lit la configuration via `Settings`;
- refuse le mode strict si `OPS_GUARD_API_KEY` est absent ou vide;
- lit le header `X-API-Key`;
- compare la clé fournie et la clé attendue avec `secrets.compare_digest`;
- retourne une erreur générique sans exposer les clés.

## Statut HTTP

Une clé absente, invalide ou non configurée en mode strict retourne HTTP `401`:

```json
{"detail": "Invalid or missing API key"}
```

`401 Unauthorized` est choisi parce que l'échec porte sur un credential d'authentification manquant ou invalide. `403 Forbidden` serait plus adapté à un client déjà authentifié mais non autorisé à exécuter une action.

## Endpoints protégés

Politique retenue: tout sauf `GET /health`.

Sont donc protégés:

- `POST /documents`;
- `GET /documents`;
- `POST /documents/upload`;
- `POST /documents/{document_id}/extract-text`;
- `POST /documents/{document_id}/chunk`;
- `POST /documents/{document_id}/embed`;
- `GET /documents/{document_id}/chunks`;
- `POST /search`;
- `POST /answer`;
- tous les endpoints `/review-tasks`;
- `POST /ai/review-tasks/suggest`;
- tous les endpoints `/audit-events`.

## Tests

Les tests existants restent centrés sur leur domaine métier grâce à un mode test explicite:

```text
REQUIRE_API_KEY=false
OPS_GUARD_API_KEY=test-api-key
```

Les tests dédiés à l'auth réactivent le mode strict via un override de `get_settings`.

Ils couvrent:

- `GET /health` public;
- refus sans clé;
- refus avec mauvaise clé;
- acceptation avec bonne clé;
- protection de AI review;
- protection des audit events;
- protection des écritures review tasks;
- absence de fuite de clé dans les erreurs;
- refus générique si la clé serveur n'est pas configurée en mode strict.

## Trade-offs

Avantages:

- protège les endpoints sensibles sans changer le modèle métier;
- simple à comprendre et à tester;
- pas de migration DB;
- pas de dépendance frontend;
- compatible avec les tests déterministes existants;
- évite d'exposer une API RAG/LLM ouverte par défaut.

Inconvénients:

- pas d'identité utilisateur;
- pas de rôles ou permissions fines;
- pas de rotation de clés;
- pas de limitation par client;
- pas d'attribution réelle dans `audit_events.actor_id`;
- une clé partagée suffit à accéder à toute l'API protégée.

## Limites acceptées

Ce bloc ne fait pas:

- utilisateurs;
- login;
- mots de passe;
- JWT;
- OAuth;
- RBAC;
- sessions;
- multi-tenant;
- dashboard admin;
- permissions avancées.

Ces limites sont acceptées pour garder l'incrément centré sur la réduction immédiate de surface publique.

## Améliorations futures

Évolutions possibles:

- remplacer la clé partagée par des utilisateurs réels;
- ajouter JWT ou sessions selon le futur frontend;
- introduire rôles et permissions;
- ajouter isolation tenant;
- attribuer les audit events à un acteur réel;
- gérer rotation et révocation des clés;
- ajouter rate limiting et monitoring de sécurité.

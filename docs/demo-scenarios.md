# Scénarios de démo actuels

Ce document décrit les démonstrations possibles avec l'état actuel d'OpsGuard AI. Il ne couvre pas encore d'upload PDF, de parsing, d'embeddings, de RAG ou d'authentification.

## Scénario 1: vérifier que l'API et la base locale fonctionnent

Objectif: montrer que le backend démarre, se connecte à PostgreSQL et expose une API testable.

### 1. Lancer PostgreSQL

Depuis la racine du repository:

```bash
docker compose up -d postgres
```

Vérifier que le service est actif:

```bash
docker compose ps
```

### 2. Lancer l'API

Dans `apps/api`:

```bash
uv run uvicorn opsguard_api.main:app --reload
```

### 3. Vérifier le health check

```bash
curl http://127.0.0.1:8000/health
```

Réponse attendue:

```json
{
  "status": "ok"
}
```

### 4. Créer une entrée document

```bash
curl -X POST http://127.0.0.1:8000/documents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "NIST Incident Response Guide",
    "source_type": "public_pdf",
    "source_path": "data/raw/nist-incident-response-guide.pdf"
  }'
```

Résultat attendu:

- statut HTTP `201`;
- un `id` généré;
- un `status` initial à `uploaded`;
- les champs `created_at` et `updated_at`.

### 5. Lister les documents

```bash
curl http://127.0.0.1:8000/documents
```

Résultat attendu:

- statut HTTP `200`;
- une liste JSON;
- le document créé dans l'étape précédente apparaît dans la liste.

## Message d'entrevue possible

À ce stade, le projet démontre une base backend propre: validation d'entrée avec Pydantic, séparation routes/services, persistance SQLAlchemy, PostgreSQL local dans Docker et tests automatisés.

L'IA n'est pas encore intégrée. C'est volontaire: le projet construit d'abord une fondation fiable avant d'ajouter l'ingestion documentaire, les embeddings et le RAG.

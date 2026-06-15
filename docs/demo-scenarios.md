# Scénarios de démo actuels

Ce document décrit les démonstrations possibles avec l'état actuel d'OpsGuard AI. Il couvre l'API de base, l'upload local minimal, l'extraction de texte, le chunking, les embeddings, la recherche sémantique et la réponse RAG avec citations. Il ne couvre pas encore l'authentification utilisateur complète, l'agentique, le tool calling ou un frontend complet.

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

## Scénario 2: téléverser un document local

Objectif: montrer que le backend reçoit un fichier PDF, Markdown ou texte brut, le sauvegarde localement, crée une entrée `Document`, puis extrait son texte.

### 1. Téléverser un Markdown

Depuis la racine du repository, créer un petit fichier de démonstration:

```bash
printf '# Security policy\n' > /tmp/security-policy.md
```

Envoyer le fichier à l'API:

```bash
curl -X POST http://127.0.0.1:8000/documents/upload \
  -F "title=Security Policy" \
  -F "file=@/tmp/security-policy.md;type=text/markdown"
```

Résultat attendu:

- statut HTTP `201`;
- `source_type` vaut `uploaded_file`;
- `status` vaut `uploaded`;
- `source_path` pointe vers un fichier dans `data/uploads/`;
- aucun chunking ou embedding n'est lancé.

### 2. Extraire le texte du document

Utiliser l'`id` retourné par l'upload:

```bash
curl -X POST http://127.0.0.1:8000/documents/2/extract-text
```

Résultat attendu:

- statut HTTP `200`;
- `status` vaut `text_extracted`;
- `extracted_text_path` pointe vers un fichier dans `data/extracted/`;
- `character_count` contient le nombre de caractères extraits;
- aucun chunking, embedding, RAG ou appel LLM n'est lancé.

## Scénario 3: chunker, embedder et répondre avec citations

Objectif: montrer le flow RAG backend sans frontend complet. Ce scénario nécessite `OPENAI_API_KEY` dans `.env`.

### 1. Chunker le document

Utiliser l'`id` du document extrait:

```bash
curl -X POST http://127.0.0.1:8000/documents/2/chunk
```

Résultat attendu:

- statut HTTP `200`;
- `status` vaut `chunked`;
- `chunk_count` est supérieur à zéro.

### 2. Générer les embeddings

```bash
curl -X POST http://127.0.0.1:8000/documents/2/embed
```

Résultat attendu:

- statut HTTP `200`;
- `status` vaut `embedded`;
- `embedded_chunk_count` correspond au nombre de chunks;
- aucun vecteur complet n'est renvoyé.

### 3. Chercher les chunks pertinents

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quel est le délai pour signaler un incident ?",
    "document_id": 2,
    "top_k": 5
  }'
```

Résultat attendu:

- statut HTTP `200`;
- une liste `results` avec les chunks les plus proches;
- des scores `similarity_score`;
- aucun embedding dans la réponse.

### 4. Demander une réponse citée

```bash
curl -X POST http://127.0.0.1:8000/answer \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quel est le délai pour signaler un incident ?",
    "document_id": 2,
    "top_k": 5
  }'
```

Résultat attendu:

- statut HTTP `200`;
- `is_answered` vaut `true` si les sources contiennent l'information;
- `citations` contient des références de chunks (`S1`, `S2`, etc.);
- `is_answered` vaut `false` si les sources ne suffisent pas;
- aucun embedding dans la réponse.

## Message d'entrevue possible

À ce stade, le projet démontre une base backend propre: validation d'entrée avec Pydantic, séparation routes/services/helpers, upload local contrôlé, extraction de texte minimale, chunking, embeddings, retrieval pgvector, réponse RAG avec citations, persistance SQLAlchemy, PostgreSQL local dans Docker et tests automatisés.

L'intégration IA reste volontairement simple: pas d'agentique, pas de tool calling, pas de LangGraph et pas de queue. Le flow actuel est synchrone et testable: route, service de réponse, service de retrieval, client LLM injectable.

# ADR-005: RAG answer with chunk citations

## Statut

Accepté.

## Contexte

OpsGuard AI possède déjà:

- des documents découpés en chunks;
- des embeddings stockés dans PostgreSQL avec pgvector;
- un endpoint `POST /search` qui récupère les chunks pertinents sans exposer les embeddings.

L'étape suivante est de produire une réponse utilisateur à partir de ces chunks, avec citations et abstention lorsque les sources ne suffisent pas.

Ce bloc ne doit pas introduire:

- agentique;
- tool calling;
- LangGraph;
- frontend complet;
- queue ou background job;
- duplication de la logique de recherche vectorielle.

## Décision

Nous ajoutons un endpoint:

```text
POST /answer
```

Le flow applicatif reste linéaire:

```text
route -> answer service -> retrieval service -> LLM client
```

La route FastAPI valide `AnswerRequest`, injecte la session DB, `Settings`, `EmbeddingClient` et `LLMClient`, puis appelle le service de réponse.

Le service `answer` orchestre:

- le retrieval;
- la construction du prompt;
- l'appel au LLM client;
- la validation de la réponse structurée;
- la conversion en `AnswerResponse`.

Le service `retrieval` appelle `search_service.semantic_search`. Il ne réimplémente pas le vector search et ne construit pas de requête pgvector parallèle.

Le client LLM est isolé dans `services/llm.py` derrière une interface testable. Les tests injectent un faux client LLM et ne font aucun appel provider réel.

## Construction du contexte

Le retrieval transforme les résultats de search en sources locales:

```text
S1, S2, S3, ...
```

Chaque source contient:

- `document_id`;
- `document_title`;
- `chunk_id`;
- `chunk_index`;
- `section_title`;
- `similarity_score`;
- un extrait du chunk.

Le contexte est borné par:

- `ANSWER_CONTEXT_MAX_CHARS`;
- `ANSWER_SOURCE_MAX_CHARS`.

Les embeddings ne sont jamais inclus dans le contexte LLM et ne sont jamais renvoyés par l'API.

## Prompt et sortie LLM

Le prompt demande au LLM d'utiliser uniquement les sources fournies et de retourner un JSON:

```json
{
  "is_answered": true,
  "answer": "...",
  "citations": ["S1"]
}
```

Si les sources ne contiennent pas l'information, le LLM doit retourner `is_answered = false` et aucune citation.

## Citations

Les citations retournées par l'API sont construites côté backend à partir des IDs de sources fournis par le LLM.

Le service accepte uniquement les citations qui existent dans le contexte courant. Une citation vers `S99`, par exemple, est rejetée si `S99` n'a pas été fourni au modèle.

Chaque citation API contient les métadonnées du chunk et l'extrait borné utilisé comme source. Elle ne contient jamais le vecteur d'embedding.

## Abstention

L'abstention est forcée par le service dans les cas suivants:

- aucun chunk embedded n'est récupéré;
- le LLM retourne `is_answered = false`;
- le LLM retourne une réponse vide;
- le LLM retourne une réponse sans citation;
- le LLM retourne une citation absente du contexte.

Dans ces cas, l'API retourne:

```json
{
  "is_answered": false,
  "answer": "Je ne sais pas d'apres les sources disponibles.",
  "citations": []
}
```

## Trade-offs

Avantages:

- architecture simple et testable;
- aucun ajout d'agentique ou d'orchestrateur;
- réutilisation stricte du semantic search existant;
- citations basées sur les chunks récupérés;
- abstention appliquée côté service;
- tests sans appel OpenAI réel.

Inconvénients:

- la qualité dépend encore du retrieval et du modèle LLM;
- il n'y a pas encore d'évaluation RAG automatisée;
- il n'y a pas encore de seuil de similarité minimal;
- le traitement est synchrone.

## Améliorations futures

Évolutions possibles:

- ajouter des évaluations retrieval/RAG;
- ajouter un seuil `min_similarity`;
- ajouter un format de citation plus riche si l'UI en a besoin;
- ajouter auth, rôles et isolation tenant avant tout usage multi-utilisateur;
- ajouter un index vectoriel quand le volume de chunks le justifie.

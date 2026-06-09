# ADR-002: Document chunking strategy

## Statut

Accepté.

## Contexte

OpsGuard AI doit transformer le texte extrait des documents en unités plus petites avant de générer des embeddings, faire du retrieval et produire des réponses avec citations.

Un découpage purement naïf, par exemple tous les 1000 caractères, serait simple mais fragile. Il risquerait de couper des phrases, de séparer un paragraphe de son titre, et de perdre le contexte nécessaire pour comprendre un passage lors du retrieval.

À ce stade, le projet ne doit pas encore ajouter d'embeddings, de RAG, d'appel LLM, d'OCR ou de parsing documentaire avancé. Le bloc actuel doit seulement couvrir:

```text
texte extrait -> chunks structurés -> PostgreSQL
```

## Décision

Nous ajoutons un chunking structure-aware minimal:

- le texte extrait est relu depuis le chemin contrôlé `EXTRACTED_TEXT_DIR/document-{document_id}.txt`;
- le texte est normalisé légèrement sans détruire les paragraphes et listes;
- les titres Markdown, titres numérotés simples et titres courts en majuscules sont détectés;
- les chunks sont construits à partir de blocs logiques séparés par lignes vides;
- le contexte de section est conservé dans `section_title` et dans le contenu du chunk;
- les limites `CHUNK_MAX_CHARS` et `CHUNK_OVERLAP_CHARS` sont configurables;
- les chunks sont persistés dans la table `document_chunks`;
- aucun embedding n'est généré dans cette étape.

Le endpoint `POST /documents/{document_id}/chunk` orchestre ce flow via la couche service. La logique de découpage vit dans `opsguard_api.services.chunking`, sans dépendance à FastAPI ou SQLAlchemy.

## Pourquoi éviter un chunking purement naïf

Un chunking par taille fixe ignore la structure du document. Dans une plateforme de revue documentaire, le titre ou la section donne souvent le sens du passage: politique de sécurité, réponse à incident, contrôle d'accès, rétention, audit, etc.

Garder cette structure dès la V1 améliore la qualité future du retrieval sans ajouter une dépendance lourde ou un parser complexe.

## Pourquoi commencer simple

Le projet est encore dans une phase progressive. Une stratégie heuristique simple est plus adaptée qu'un parsing avancé parce qu'elle est:

- facile à tester;
- compréhensible en entrevue;
- extensible;
- suffisante pour les documents Markdown, texte brut et PDF simples;
- compatible avec les prochaines étapes embeddings et citations.

## Pourquoi stocker les chunks sans embeddings

Les chunks sont une étape métier indépendante. Les stocker maintenant permet de valider:

- la qualité du découpage;
- l'idempotence du re-chunking;
- les relations DB entre documents et chunks;
- les futurs contrats nécessaires au retrieval.

Les embeddings viendront ensuite, probablement dans une table dédiée ou une colonne liée aux chunks selon la stratégie retenue.

## Idempotence

Le re-chunking suit une stratégie simple:

```text
delete existing chunks for document
recreate chunks
commit
```

Ce choix évite les doublons et garde une V1 claire. Plus tard, avec des embeddings, il faudra décider si le re-chunking supprime aussi les embeddings, crée une nouvelle version de chunks, ou invalide les anciennes représentations.

## Trade-offs

Avantages:

- meilleure conservation du contexte qu'un split fixe;
- pas de dépendance externe lourde;
- logique pure testable hors DB;
- réponse API courte qui ne renvoie pas tout le contenu;
- base prête pour embeddings et retrieval.

Inconvénients:

- heuristiques imparfaites pour les PDF mal structurés;
- pas de parsing avancé de tableaux;
- pas d'estimation de tokens;
- offsets calculés sur le texte normalisé plutôt que sur le fichier source original;
- `create_all()` reste temporaire et ne remplace pas Alembic.

## Limites actuelles

Le chunker ne comprend pas encore:

- la structure PDF réelle;
- les tableaux;
- les en-têtes/pieds de page;
- les sections imbriquées complexes;
- la langue du document;
- les limites exactes par tokens de modèle.

## Améliorations futures

Évolutions possibles:

- ajouter Alembic pour versionner la table `document_chunks`;
- ajouter `token_estimate`;
- enrichir les métadonnées avec page, source, heading path et hash de contenu;
- dédupliquer les headers/footers récurrents;
- gérer les tableaux avec une stratégie dédiée;
- générer des embeddings pour chaque chunk;
- ajouter des évaluations de chunking et retrieval;
- versionner les chunks pour garder l'historique des re-chunkings.

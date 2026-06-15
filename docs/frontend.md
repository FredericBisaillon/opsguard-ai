# Frontend Review Console

La Review Console Next.js vit dans `apps/web`. Elle donne une premiere surface
produit pour piloter le backend OpsGuard AI sans ajouter encore
d'authentification complete.

## Objectif

La console permet de faire une demo end-to-end:

1. verifier la sante de l'API avec `GET /health`;
2. saisir une API key locale pour les endpoints proteges;
3. uploader un document;
4. lancer `extract-text`, `chunk` puis `embed`;
5. poser une question RAG via `POST /answer`;
6. demander une suggestion via `POST /ai/review-tasks/suggest`;
7. consulter les review tasks et dismiss une task;
8. consulter les audit events recents.

Ce frontend reste volontairement minimal. Il n'ajoute pas de login, JWT, roles,
multi-tenant, workflow d'approbation complet, viewer PDF, websocket ou dashboard
analytique.

## Lancement local

Lancer d'abord PostgreSQL et le backend:

```bash
docker compose up -d postgres
cd apps/api
uv run uvicorn --app-dir src opsguard_api.main:app --reload
```

Puis lancer le frontend:

```bash
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

Ouvrir:

```text
http://localhost:3000
```

## Configuration frontend

`apps/web/.env.local` peut definir:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Les variables `NEXT_PUBLIC_*` sont exposees au navigateur par Next.js. Ne jamais
y mettre de secret.

## API key dans le navigateur

La console demande la valeur attendue par le backend pour le header
`X-API-Key`. Elle la stocke dans `localStorage` sous une cle locale et l'ajoute
aux appels proteges.

La cle complete n'est pas affichee apres sauvegarde, n'est pas placee dans les
URLs et n'est pas loggee par le code frontend. Le bouton `Clear` supprime la
valeur du navigateur.

Cette solution est uniquement une commodite de developpement/demo. En
production, il faudra remplacer ce mecanisme par une vraie authentification,
une gestion de session, des roles et une politique de rotation.

## CORS local

Le backend expose un parametre:

```env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Il autorise la console locale a appeler l'API avec le header `X-API-Key`.
Limiter cette liste aux origins necessaires.

## Flow demo recommande

1. Saisir la meme cle que `OPS_GUARD_API_KEY`.
2. Cliquer `Check API`.
3. Uploader un fichier `.pdf`, `.md` ou `.txt`.
4. Sur le document cree, cliquer `Extract text`, puis `Chunk`, puis `Embed`.
5. Poser une question dans `RAG question`.
6. Dans `AI review suggestion`, selectionner le document et tester une query
   comme "Identify the most important review task for this document".
7. Activer `Auto-create` pour verifier la creation d'une task validee.
8. Consulter `Tasks / Audit` pour voir la task et les events.

Les appels RAG, embeddings et suggestions IA requierent `OPENAI_API_KEY` cote
backend.

# OpsGuard AI Web

Frontend Next.js pour la Review Console minimale d'OpsGuard AI.

La console sert a demontrer le flow principal du produit:

- verifier `GET /health`;
- configurer temporairement une API key locale;
- lister et uploader des documents;
- lancer extraction, chunking et embeddings;
- poser une question RAG avec citations;
- demander une suggestion de review task;
- consulter et dismiss des review tasks;
- lire les audit events recents.

Elle n'implemente pas encore de login, JWT, roles, multi-tenant, workflow
d'approbation complet, viewer PDF ou realtime.

## Configuration

Copier l'exemple local:

```bash
cp .env.example .env.local
```

Variable disponible:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Cette URL est publique dans le bundle navigateur. La valeur par defaut du code
est aussi `http://localhost:8000`.

## API key locale

Le backend protege les endpoints applicatifs avec `X-API-Key` quand
`REQUIRE_API_KEY=true`.

La console permet de saisir la cle dans le navigateur et la stocke dans
`localStorage`. Apres sauvegarde, la cle complete n'est plus affichee dans
l'interface. Le bouton `Clear` la retire du stockage local.

Cette approche est uniquement acceptable pour le developpement et la demo
portfolio. Ce n'est pas une authentification production.

## Lancement

Depuis `apps/web`:

```bash
pnpm install
pnpm dev
```

Ouvrir:

```text
http://localhost:3000
```

Le backend doit tourner separement sur l'URL configuree par
`NEXT_PUBLIC_API_BASE_URL`.

## Validation

Depuis `apps/web`:

```bash
pnpm lint
pnpm build
```

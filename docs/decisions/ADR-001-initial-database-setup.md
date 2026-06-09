# ADR-001: Initial database setup

## Statut

Accepté.

## Contexte

OpsGuard AI a besoin d'une base de données relationnelle pour stocker progressivement les documents, puis plus tard les chunks, embeddings, tâches de revue, utilisateurs, rôles et métadonnées de sécurité.

À ce stade, le projet doit rester simple, localement reproductible et facile à expliquer en entrevue. Il ne doit pas encore introduire toute la complexité d'un système de production.

## Décision

Nous utilisons:

- PostgreSQL comme base de données principale;
- Docker Compose pour lancer PostgreSQL localement;
- l'image `pgvector/pgvector:pg16`;
- SQLAlchemy comme ORM et couche d'accès SQL;
- psycopg comme driver PostgreSQL;
- Pydantic pour les contrats d'entrée et de sortie de l'API;
- `SQLAlchemy.create_all()` temporairement pour créer les tables au démarrage.

## Pourquoi PostgreSQL

PostgreSQL est un bon choix pour OpsGuard AI parce qu'il permet de combiner:

- données relationnelles classiques;
- contraintes de schéma;
- requêtes SQL robustes;
- extensions comme pgvector;
- évolution future vers une architecture plus proche de la production.

Le projet aura besoin de stocker des objets structurés: documents, chunks, statuts, tâches de revue, utilisateurs et permissions. PostgreSQL est adapté à ce type de système.

## Pourquoi SQLAlchemy

SQLAlchemy donne une couche explicite entre le code Python et la base de données. Il permet de:

- modéliser les tables avec des classes Python;
- garder les requêtes lisibles;
- gérer les sessions et transactions;
- éviter de disperser du SQL brut dans les routes HTTP;
- préparer une transition naturelle vers Alembic pour les migrations.

Le projet reste ainsi compréhensible pour un backend Python moderne.

## Pourquoi séparer Pydantic et SQLAlchemy

Les modèles SQLAlchemy décrivent la persistance. Les schemas Pydantic décrivent les contrats API.

Cette séparation est volontaire:

- les champs exposés par l'API ne doivent pas forcément être identiques aux colonnes SQL;
- la validation d'entrée appartient à Pydantic;
- les contraintes de stockage appartiennent à SQLAlchemy et PostgreSQL;
- le modèle public de l'API peut évoluer sans exposer toute la structure interne.

Dans le projet actuel:

- `DocumentCreate` valide le payload entrant;
- `DocumentRead` définit la réponse HTTP;
- `Document` représente la table `documents`.

## Pourquoi Docker local

Docker Compose rend le setup local reproductible. Un développeur peut lancer PostgreSQL sans installer PostgreSQL directement sur sa machine.

Cela permet aussi de garder la configuration proche d'un environnement réel:

- service PostgreSQL dédié;
- variables d'environnement;
- volume persistant;
- healthcheck;
- port local configurable.

## Pourquoi pgvector maintenant

pgvector est activé maintenant pour préparer la future recherche sémantique.

Même si le projet ne stocke pas encore d'embeddings, l'extension est déjà disponible dans la base locale. Cela réduit le risque d'intégration au moment où les tables de chunks et embeddings seront ajoutées.

Important: l'activation de pgvector ne signifie pas que le projet fait déjà du RAG ou de la recherche vectorielle.

## Pourquoi `create_all()` est acceptable temporairement

`create_all()` est acceptable à ce stade parce que:

- le schéma est très petit;
- le projet est en phase d'apprentissage et de prototypage;
- il n'y a pas encore de migrations historiques à maintenir;
- cela garde le setup local simple.

Cette décision est temporaire.

Avant d'ajouter un schéma plus complexe, il faudra passer à Alembic pour gérer les migrations de manière contrôlée.

## Trade-offs

Avantages:

- setup local simple;
- architecture claire;
- pile backend sérieuse;
- préparation à pgvector;
- séparation propre entre API, service et persistance.

Inconvénients:

- `create_all()` ne remplace pas un vrai système de migrations;
- les tests ne sont pas encore totalement isolés de la base locale;
- pgvector est activé avant d'être utilisé fonctionnellement;
- la configuration reste locale et non prête pour la production.

## Décision future

Avant d'ajouter les tables de chunks, embeddings, tâches de revue ou utilisateurs, le projet devra introduire Alembic.

Alembic permettra de:

- versionner les changements de schéma;
- appliquer les migrations de manière répétable;
- faciliter la collaboration;
- mieux représenter une pratique backend professionnelle.

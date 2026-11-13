# ClubIA v2 — Assistant multi-agents pour clubs étudiants

Dans un club étudiant, les décisions se prennent en réunion, mais on oublie vite qui devait faire quoi et pour quand. ClubIA résout ce problème avec une IA générative organisée en **agents LangGraph** qui accèdent aux données via un **serveur MCP**.

On importe le compte-rendu d'une réunion (texte collé, PDF ou **enregistrement audio**), et l'application :

1. **transcrit** l'audio (Whisper) ;
2. rédige un **résumé**, liste les **décisions** et extrait les **tâches** (qui, quoi, pour quand). Les dates relatives comme « vendredi prochain » sont converties en vraies dates ;
3. **rattache les responsables aux membres du club** (« Karim B. » → Karim) ;
4. **suit l'avancement** des tâches et signale les **retards** ;
5. répond aux questions et **agit sur les tâches** en langage naturel, avec une équipe d'agents : archiviste (**RAG** avec sources), gestionnaire des tâches, analyste.

---

## Nouveautés de la v2

| Avant (v1) | Maintenant (v2) |
|---|---|
| Un seul appel LLM par compte-rendu, tronqué à 15 000 caractères | **Graphe LangGraph d'ingestion** : comptes-rendus longs découpés et analysés **en parallèle** (map-reduce), indexation RAG en parallèle, nouvelles tentatives automatiques si le JSON est invalide |
| Import bloquant (30 s d'attente) | Analyse **en tâche de fond**, l'interface suit le statut |
| Un chat RAG unique | **Chat multi-agents** : un superviseur choisit l'archiviste (RAG), le gestionnaire des tâches (agent ReAct qui **modifie** les tâches) et/ou l'analyste ; les réponses sont fusionnées |
| Pas de mémoire de conversation | **Mémoire** par conversation (checkpointer LangGraph SQLite) : « et celle de Sarah ? » fonctionne |
| Backend qui lit SQLite et ChromaDB directement | **Serveur MCP** = seule porte d'accès aux données (18 outils, 2 ressources, 1 prompt), utilisable aussi depuis n'importe quel client MCP (assistant de bureau, IDE) |
| « Karim » et « Karim B. » = deux membres | **Normalisation des membres** (alias, même prénom, fautes de frappe) + page Membres (fusion, alias) |
| Pas de tests | **33 tests** (unitaires, protocole MCP, bout en bout avec le vrai serveur MCP) |
| Lancement manuel | **Docker**, **Docker Compose**, **Kubernetes** (Kustomize) et **pipeline Jenkins** complet |

Le **RAG** est conservé : recherche sémantique ChromaDB (embeddings locaux `all-MiniLM-L6-v2`) côté serveur MCP, génération avec citations `[1]`, `[2]` côté agent archiviste.

---

## Architecture

```
                         ┌──────────────────────── Backend FastAPI ────────────────────────┐
┌────────────┐  /api     │                                                                 │
│  Frontend  │ ────────► │  Graphe d'ingestion (LangGraph)    Graphe de chat (LangGraph)   │
│ React/Vite │ ◄──────── │  load → prepare ─┬─► index ──┐     supervisor ─┬─► historian ─┐  │
│  (Nginx)   │           │                  └─► extract×N ─► merge         ├─► task_manager┼─► synthesizer
└────────────┘           │                      → normalize → persist     └─► analyst ───┘  │
                         │                                                                 │
                         │  Client MCP (stdio en local, streamable HTTP en conteneur)      │
                         └───────────────────────────────┬─────────────────────────────────┘
                                                         │ protocole MCP
                         ┌───────────────────────────────▼─────────────────────────────────┐
                         │  Serveur MCP « clubia » (FastMCP)                               │
                         │  outils : search_meetings, list/create/update_task, get_stats,  │
                         │           list/merge_members, create/index/complete_meeting...  │
                         │  ├─ SQLite   (réunions, tâches, membres)                         │
                         │  └─ ChromaDB (index RAG des comptes-rendus)                      │
                         └─────────────────────────────────────────────────────────────────┘
                                  LLM : Llama 3.3 70B via Groq (LangChain ChatGroq) · Whisper via Groq
```

### Pourquoi le serveur MCP détient les données

ChromaDB ne supporte pas d'être ouvert par deux processus à la fois (testé : le second lecteur échoue avec « Nothing found on disk »). Le serveur MCP est donc **le seul processus qui ouvre SQLite et ChromaDB**. Le backend et les agents passent tous par lui. On y gagne :

- une **frontière nette** : les agents ne voient que les outils qu'on leur donne (liste blanche : l'agent des tâches ne peut ni supprimer ni ingérer) ;
- un serveur **réutilisable** par n'importe quel client MCP (assistant de bureau, IDE…) ;
- un backend **sans état métier**, facile à redéployer.

### Graphe d'ingestion

| Nœud | Rôle |
|---|---|
| `load` | Texte collé, PDF (pypdf), TXT, ou audio transcrit par Whisper (minute par minute) |
| `prepare` | Découpe le texte en parties de 12 000 caractères maximum, coupées en fin de phrase |
| `index` | Indexation RAG via l'outil MCP `index_meeting`, **en parallèle** de l'extraction |
| `extract_part` ×N | Une instance par partie (API `Send` de LangGraph) ; JSON validé par Pydantic ; `RetryPolicy` (3 essais) |
| `merge` | Fusionne les résumés partiels (un appel LLM seulement s'il y a plusieurs parties) |
| `normalize` | Dates validées, tâches vides et doublons supprimés, échéances suspectes signalées |
| `persist` | **Jointure** : attend `index` et `normalize`, puis appelle `complete_meeting` |

En cas d'erreur, la réunion passe en statut `error` avec le message, visible dans l'interface.

### Graphe de chat multi-agents

| Agent | Ce qu'il fait | Outils MCP |
|---|---|---|
| **Superviseur** | Choisit un ou plusieurs agents (sortie JSON validée) ; routage par mots-clés en secours | — |
| **Archiviste** (RAG) | Reformule la question si elle dépend de l'historique, cherche, répond en citant `[n]` | `search_meetings` |
| **Gestionnaire des tâches** | Agent ReAct (boucle LLM ⇄ outils) : consulter, créer, modifier, réattribuer | `list_tasks`, `create_task`, `update_task`, `list_members`, `list_meetings`, `get_meeting` |
| **Analyste** | Bilan chiffré, retards, charge par membre, priorités | `get_stats`, `list_tasks` |
| **Synthèse** | Fusionne les rapports (aucun appel LLM s'il n'y en a qu'un) | — |

Les agents choisis s'exécutent **en parallèle**. La réponse renvoie aussi la **trace** (agents, outils appelés et arguments), affichée dans l'interface.

---

## Structure du projet

```
clubia/
├── mcp_server/                 # Serveur MCP = couche données
│   ├── server.py               # 18 outils, 2 ressources, 1 prompt (FastMCP), sonde /healthz
│   ├── database.py             # SQLite : réunions, tâches, membres, statistiques
│   ├── members.py              # Normalisation des noms (alias, prénom, fautes de frappe)
│   ├── rag.py                  # Index ChromaDB : indexation et recherche
│   ├── tests/                  # Tests base, membres, protocole MCP, RAG
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── main.py             # API FastAPI (routes, sondes, tâche de fond)
│   │   ├── mcp_client.py       # Session MCP persistante, reconnexion, outils LangChain
│   │   ├── schemas.py          # Schémas Pydantic (sorties LLM, requêtes)
│   │   ├── agents/
│   │   │   ├── ingestion.py    # Graphe LangGraph d'ingestion (map-reduce)
│   │   │   ├── chat.py         # Graphe LangGraph multi-agents
│   │   │   └── prompts.py      # Tous les prompts
│   │   └── services/           # documents (PDF/texte), transcription (Whisper), llm (ChatGroq)
│   ├── tests/                  # Graphes avec faux LLM + test de bout en bout de l'API
│   └── Dockerfile
├── frontend/                   # React + Vite ; Dockerfile Nginx (non root) + nginx.conf.template
├── k8s/
│   ├── base/                   # Deployments, Services, PVC, Ingress, HPA, NetworkPolicies
│   └── overlays/               # staging, production (Kustomize)
├── docker-compose.yml
├── Jenkinsfile
├── pyproject.toml              # Config pytest + ruff
└── requirements-dev.txt
```

---

## Lancement en local

### Prérequis

- Python 3.11 ou plus récent, Node.js 18 ou plus récent
- Une clé API Groq gratuite : https://console.groq.com/keys

### Installation

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/Mac : source .venv/bin/activate
pip install -r ../requirements-dev.txt
copy .env.example .env          # Linux/Mac : cp .env.example .env
```

Ouvre `backend/.env` et colle ta clé dans `GROQ_API_KEY=`.

```bash
cd frontend
npm install
```

### Démarrage

**Sous Windows :** double-clique sur `start.bat`. Sinon, dans deux terminaux :

```bash
cd backend && uvicorn app.main:app --reload --reload-dir app --port 8001
```

```bash
cd frontend && npm run dev
```

Puis ouvre **http://localhost:5174** (API : http://localhost:8001/docs). En local, le backend lance lui-même le serveur MCP (`python -m mcp_server`, transport stdio). Les données sont dans `clubia/data/`.

### Utiliser le serveur MCP depuis un autre client MCP

```json
{
  "mcpServers": {
    "clubia": {
      "command": "C:\\chemin\\vers\\clubia\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server"],
      "cwd": "C:\\chemin\\vers\\clubia"
    }
  }
}
```

### Tests et qualité

```bash
pytest
```

```bash
ruff check .
```

(à lancer depuis `clubia/`). Les tests n'appellent jamais Groq : le LLM est remplacé par un faux modèle scripté. Le test de bout en bout lance le vrai serveur MCP avec un dossier de données temporaire.

---

## Docker

```bash
docker compose up --build
```

Puis ouvre **http://localhost:8080**. Trois images :

| Image | Contenu | Port |
|---|---|---|
| `clubia-mcp` | Serveur MCP (streamable HTTP), modèle d'embedding téléchargé au build, volume `/data` | 8765 |
| `clubia-backend` | API + agents, client MCP HTTP, volume `/state` (mémoire des conversations) | 8001 |
| `clubia-frontend` | Build Vite servi par Nginx non root, proxy `/api` → backend | 8080 |

Toutes tournent avec un utilisateur non root, avec des builds multi-étapes et des healthchecks.

---

## Kubernetes

```bash
kubectl create namespace clubia
```

```bash
kubectl -n clubia create secret generic clubia-secrets --from-literal=GROQ_API_KEY=gsk_...
```

```bash
kubectl apply -k k8s/overlays/production
```

- **mcp-server** : 1 réplique (SQLite + ChromaDB sur un PVC `ReadWriteOnce`, stratégie `Recreate`), sondes `/healthz`.
- **backend** : sonde de vie `/api/health`, sonde de disponibilité `/api/ready` (ping MCP), système de fichiers en lecture seule, reconnexion MCP automatique si le serveur redémarre.
- **frontend** : 2 réplicas + HPA (2 à 5 selon le CPU), rolling update sans interruption.
- **NetworkPolicies** : seul le backend joint le serveur MCP, seul le frontend joint le backend.
- **Ingress** Nginx (TLS via cert-manager en production), `securityContext` durcis (non root, `seccomp`, capacités supprimées).
- Overlays **staging** (namespace `clubia-staging`, logs DEBUG, 1 réplique frontend) et **production** (TLS, volume 10 Gi).

---

## CI/CD Jenkins

Le `Jenkinsfile` (job multibranch, *Script Path* `clubia/Jenkinsfile`) enchaîne :

| Étape | Détail |
|---|---|
| Checkout | Tag d'image `<build>-<commit>` |
| Qualité (en parallèle) | `ruff` + `pytest` avec couverture (rapports JUnit) · `npm ci && npm run build` · rendu Kustomize des overlays |
| Images Docker | Build parallèle des 3 images, labels OCI |
| Scan Trivy | Vulnérabilités HIGH/CRITICAL (bloquant si `FAIL_ON_VULNERABILITIES`) |
| Publication | `docker push` vers le registre (branches `main` et `develop`) |
| Déploiement staging | Namespace + Secret (depuis le credential `groq-api-key`), `kustomize edit set image`, `kubectl apply -k`, `rollout status`, test de fumée |
| Validation | Approbation manuelle (`input`) avant la production (`main`) |
| Déploiement production | Même procédure ; **rollback automatique** (`rollout undo`) en cas d'échec |

Credentials Jenkins attendus : `docker-registry`, `kubeconfig-staging`, `kubeconfig-prod`, `groq-api-key`. L'agent n'a besoin que de Docker : Python, Node, Trivy, kubectl et kustomize tournent dans des conteneurs.

---

## API

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/health` · `/api/ready` | Sondes de vie et de disponibilité (ping MCP) |
| GET | `/api/stats` | Chiffres du tableau de bord |
| GET | `/api/mcp/tools` | Outils exposés par le serveur MCP |
| GET / POST | `/api/meetings` | Liste · import (`202`, analyse en tâche de fond) |
| GET / DELETE | `/api/meetings/{id}` | Détail (statut `processing` / `ready` / `error`) · suppression |
| GET / POST | `/api/tasks` | Liste (filtres `status`, `assignee`, `overdue`) · création |
| PATCH / DELETE | `/api/tasks/{id}` | Modification partielle · suppression (404 si introuvable) |
| GET / POST | `/api/members` | Liste · création |
| PATCH / DELETE | `/api/members/{id}` | Renommer (met à jour les tâches), alias, e-mail · supprimer |
| POST | `/api/members/{id}/merge` | Fusionner une autre fiche dans celle-ci |
| POST | `/api/chat` | Question aux agents (`question`, `language`, `thread_id`) → réponse, sources, agents, trace |

---

## Limites

- Le serveur MCP et le backend tournent chacun en **une seule réplique** (SQLite/ChromaDB et checkpointer SQLite). Pour monter en charge : PostgreSQL + pgvector et un checkpointer Postgres.
- Le calcul des dates relatives reste fait par le LLM ; les échéances incohérentes sont signalées et modifiables.
- Le modèle d'embedding `all-MiniLM-L6-v2` est surtout entraîné sur l'anglais.
- Pas encore de comptes utilisateurs ni de gestion de plusieurs clubs.

## Perspectives

- Streaming des étapes des agents (SSE) pendant la réponse.
- Rappels par e-mail avant les échéances (un agent planifié qui utilise les outils MCP).
- Diarisation de l'audio, embeddings multilingues, mode 100 % local avec Ollama.

# RevisIA v2 — Assistant de révision multi-agents avec graphe de connaissances

RevisIA aide un étudiant à réviser ses cours avec une IA générative organisée en **agents LangGraph**, qui accèdent aux données via un **serveur MCP**, et un **graphe de connaissances** (Neo4j) qui relie les cours entre eux.

L'étudiant importe un cours (PDF, texte, **enregistrement audio**, ou texte collé), et l'application :

1. **transcrit** l'audio (Whisper) ;
2. **découpe le cours en chapitres** et extrait pour chacun : les **notions enseignées**, les **compétences à acquérir** et les **prérequis** ;
3. construit un **graphe de connaissances** (cours → chapitres → notions / compétences / prérequis) ;
4. **relie chaque chapitre aux chapitres précédents dont il dépend** : dans le même cours, ou dans un cours placé **avant** dans le cursus (jamais vers un chapitre suivant) ;
5. propose un **parcours de révision** : quels chapitres revoir, dans quel ordre, avant d'attaquer un chapitre ;
6. génère un **résumé**, les **notions clés** et un **quiz** ;
7. répond aux questions avec une équipe d'agents : tuteur (**RAG** avec sources), navigateur du graphe, examinateur (quiz à la demande).

---

## Nouveautés de la v2

| Avant (v1) | Maintenant (v2) |
|---|---|
| Un seul appel LLM, cours tronqué à 15 000 caractères | **Graphe LangGraph d'ingestion** : découpage en chapitres, analyse des chapitres **en parallèle**, indexation RAG en parallèle, nouvelles tentatives automatiques |
| Notions clés en liste plate | **Graphe de connaissances** (modèle Neo4j) : chapitres, notions, **compétences à acquérir**, **prérequis** |
| Cours isolés | **Liens entre cours** : un agent relie chaque chapitre aux chapitres **précédents** qui enseignent ses prérequis (correspondance exacte ou sémantique, validée par le LLM) |
| — | **Parcours de révision** calculé sur le graphe (dépendances directes et indirectes) |
| — | **Visualisation interactive du graphe** (style navigateur Neo4j : zoom, glisser, détails, parcours) |
| Import bloquant (30 s) | Analyse **en tâche de fond** |
| Un chat RAG | **Chat multi-agents** (superviseur + tuteur RAG + navigateur du graphe + examinateur) avec **mémoire** |
| Backend qui lit SQLite / ChromaDB | **Serveur MCP** = seule porte d'accès aux données (18 outils, 1 ressource, 1 prompt) |
| Pas de tests | **29 tests** (graphe, règles d'ordre, protocole MCP, agents, bout en bout) + test d'intégration Neo4j en CI |
| Lancement manuel | **Docker**, **Docker Compose** (avec Neo4j), **Kubernetes** (Kustomize) et **pipeline Jenkins** |

Le **RAG** est conservé : recherche sémantique ChromaDB (embeddings locaux `all-MiniLM-L6-v2`) côté serveur MCP, réponses avec citations `[1]`, `[2]` (page du PDF ou minute de l'audio).

---

## Le graphe de connaissances

```
(:Course)-[:HAS_CHAPTER]->(:Chapter)-[:NEXT]->(:Chapter)
(:Chapter)-[:COVERS]->(:Concept)          notion enseignée
(:Chapter)-[:TEACHES]->(:Skill)           compétence à acquérir
(:Chapter)-[:REQUIRES]->(:Concept)        prérequis
(:Chapter)-[:DEPENDS_ON {reason, concepts}]->(:Chapter)   toujours vers un chapitre PRÉCÉDENT
```

- Les **notions sont partagées** entre cours : « Clé primaire » enseignée dans *Bases de données* et demandée par *Python pour la data* est le **même nœud**.
- **Règle d'ordre** : chaque cours a une place dans le cursus, chaque chapitre une place dans son cours. Un `DEPENDS_ON` n'est accepté que vers un chapitre qui précède (le serveur MCP refuse les autres). Le graphe des dépendances reste donc **sans cycle**. Changer l'ordre du cursus supprime les liens devenus invalides.
- **Deux moteurs, même interface** : **Neo4j** (requêtes Cypher, parcours par chemins de longueur variable `[:DEPENDS_ON*1..20]`) quand `NEO4J_URI` est défini (Docker, Kubernetes), sinon des **tables SQLite** (développement local, tests). Un test d'intégration vérifie que les deux donnent les mêmes résultats.

### Comment les liens entre chapitres sont trouvés (agent linker)

```
gather ──► (liens sémantiques à vérifier ?) ──► validate ──► apply
```

1. **gather** : pour chaque prérequis d'un chapitre, l'outil MCP `find_prerequisite_candidates` cherche les chapitres **précédents** qui l'enseignent : même nom de notion (correspondance exacte, acceptée directement), ou notion proche par **embeddings** (« Jointure SQL » ≈ « Jointure »).
2. **validate** : un seul appel LLM confirme ou rejette les correspondances sémantiques (évite les faux liens sur un mot commun). Si le LLM échoue, seules les correspondances très proches (score ≥ 0,8) sont gardées.
3. **apply** : création des relations `DEPENDS_ON` avec leur raison.

Le bouton **« Relier aux cours précédents »** relance cet agent (utile après avoir importé un cours de base plus tard et l'avoir remonté dans le cursus).

---

## Architecture

```
┌────────────┐ /api ┌──────────────────────────── Backend FastAPI ──────────────────────────────┐
│  Frontend  │ ───► │ Ingestion (LangGraph)                     Chat (LangGraph)                │
│ React/Vite │ ◄─── │ load → structure ─┬─► index ─────┐         supervisor ─┬─► tutor ──────┐   │
│ + graphe   │      │                   └─► analyze ×N ─► synthesize        ├─► navigator ──┼─► synthesizer
│  d3-force  │      │                         → persist → linker (agent)    └─► quizmaster ─┘   │
│  (Nginx)   │      │ Client MCP (stdio en local, streamable HTTP en conteneur)                 │
└────────────┘      └───────────────────────────────────┬───────────────────────────────────────┘
                                                        │ protocole MCP
                    ┌───────────────────────────────────▼───────────────────────────────────────┐
                    │ Serveur MCP « revisia » : search_courses, get_chapter, learning_path,      │
                    │ find_prerequisite_candidates, add_dependency, get_knowledge_graph, ...    │
                    │  ├─ SQLite   (cours, chapitres, quiz)                                      │
                    │  ├─ ChromaDB (passages des cours + notions des chapitres)                  │
                    │  └─ Neo4j    (graphe de connaissances)  — ou tables SQLite en local        │
                    └────────────────────────────────────────────────────────────────────────────┘
                         LLM : Llama 3.3 70B via Groq (LangChain ChatGroq) · Whisper via Groq
```

### Graphe d'ingestion

| Nœud | Rôle |
|---|---|
| `load` | Texte collé, PDF (une section par page), TXT, ou audio transcrit minute par minute |
| `structure` | Découpe en chapitres sur les titres (« Chapitre 2 », « Partie II », « # Titre », « 3. … ») avec la plage de pages ; sinon par taille |
| `index` | Indexation RAG via MCP, **en parallèle** de l'analyse |
| `analyze_chapter` ×N | Une instance par chapitre (API `Send`) : titre, résumé, notions, compétences, prérequis — JSON validé par Pydantic, `RetryPolicy` |
| `synthesize` | Résumé du cours, notions clés, quiz (à partir des résumés des chapitres : aucun texte tronqué) |
| `persist` | Jointure (`index` + `synthesize`) : enregistre le cours et construit son sous-graphe |
| `link` | Agent linker : dépendances vers les chapitres précédents |

### Agents du chat

| Agent | Rôle | Outils MCP |
|---|---|---|
| **Superviseur** | Choisit un ou plusieurs agents (JSON validé, routage par mots-clés en secours) | — |
| **Tuteur** (RAG) | Explique en citant les passages `[n]` ; reformule les questions de suivi | `search_courses` |
| **Navigateur** | Agent ReAct sur le graphe : prérequis, compétences, parcours, où une notion est enseignée | `list_courses`, `list_chapters`, `get_chapter`, `learning_path`, `find_concept`, `graph_stats` |
| **Examinateur** | Quiz d'entraînement sur un sujet, affiché de façon interactive | `search_courses` |
| **Synthèse** | Fusionne les rapports | — |

---

## Structure du projet

```
revisia/
├── mcp_server/
│   ├── server.py         # 18 outils MCP, ressource, prompt, sonde /healthz
│   ├── graph_store.py    # Graphe : SqliteGraphStore et Neo4jGraphStore (Cypher)
│   ├── database.py       # SQLite : cours, chapitres, ordre du cursus
│   ├── rag.py            # ChromaDB : passages et notions
│   └── tests/            # Graphe, règles d'ordre, protocole MCP, intégration Neo4j
├── backend/app/
│   ├── main.py           # API FastAPI
│   ├── mcp_client.py     # Session MCP persistante, reconnexion, outils LangChain
│   ├── agents/           # ingestion.py, linker.py, chat.py, prompts.py
│   └── services/         # documents (chapitres, morceaux), transcription, llm
├── frontend/src/components/
│   ├── GraphView.jsx     # Graphe interactif (d3-force) + détails + parcours
│   ├── CourseView.jsx    # Résumé, chapitres & compétences, graphe du cours, quiz
│   └── ChatPanel.jsx     # Chat multi-agents (trace, sources, quiz interactif)
├── k8s/                  # base (Neo4j StatefulSet, MCP, backend, frontend, Ingress, HPA, NetworkPolicies) + overlays
├── docker-compose.yml    # Neo4j + MCP + backend + frontend
└── Jenkinsfile
```

---

## Lancement en local

Prérequis : Python 3.11+, Node.js 18+, une clé Groq gratuite (https://console.groq.com/keys).

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/Mac : source .venv/bin/activate
pip install -r ../requirements-dev.txt
copy .env.example .env          # puis colle ta clé dans GROQ_API_KEY=
```

```bash
cd frontend && npm install
```

Sous Windows : double-clique sur `start.bat`. Puis ouvre **http://localhost:5173** (API : http://localhost:8000/docs). En local, le backend lance lui-même le serveur MCP et le graphe est stocké dans SQLite (`revisia/data/`). Pour utiliser Neo4j en local, renseigne `NEO4J_URI`, `NEO4J_USER` et `NEO4J_PASSWORD` dans `backend/.env`.

**Tests et qualité** (depuis `revisia/`) :

```bash
pytest
```

```bash
ruff check .
```

Le LLM est remplacé par un faux modèle dans les tests. Le test Neo4j est ignoré sans `NEO4J_TEST_URI`, et Jenkins le lance avec un conteneur `neo4j:5.26-community`.

---

## Docker

```bash
docker compose up --build
```

- Application : **http://localhost:8080**
- **Neo4j Browser** : **http://localhost:7474** (utilisateur `neo4j`, mot de passe `NEO4J_PASSWORD`, `revisia-neo4j` par défaut). Exemples de requêtes Cypher :

```cypher
MATCH p = (c:Chapter)-[:DEPENDS_ON*]->(:Chapter) RETURN p
```

```cypher
MATCH (ch:Chapter)-[:TEACHES]->(s:Skill) RETURN ch.label, collect(s.label)
```

Quatre conteneurs : `neo4j`, `revisia-mcp` (modèle d'embedding téléchargé au build), `revisia-backend`, `revisia-frontend` (Nginx non root, proxy `/api`).

---

## Kubernetes

```bash
kubectl create namespace revisia
```

```bash
kubectl -n revisia create secret generic revisia-secrets --from-literal=GROQ_API_KEY=gsk_... --from-literal=NEO4J_PASSWORD=...
```

```bash
kubectl apply -k k8s/overlays/production
```

- **Neo4j** : StatefulSet avec volume persistant (5 Gi, 20 Gi en production), mot de passe depuis le Secret.
- **mcp-server** : 1 réplique (SQLite + ChromaDB sur PVC), attend Neo4j au démarrage.
- **backend** : sondes `/api/health` et `/api/ready` (ping MCP), système de fichiers en lecture seule, reconnexion MCP automatique.
- **frontend** : 2 réplicas + HPA, rolling update sans interruption.
- **NetworkPolicies** : frontend → backend → serveur MCP → Neo4j, rien d'autre.
- Overlays **staging** et **production** (TLS cert-manager).

---

## CI/CD Jenkins

`Jenkinsfile` (job multibranch, *Script Path* `revisia/Jenkinsfile`) :

| Étape | Détail |
|---|---|
| Qualité (parallèle) | `ruff` + `pytest` avec couverture **et un vrai Neo4j** en conteneur · build du frontend · rendu Kustomize des overlays |
| Images Docker | Build parallèle des 3 images |
| Scan Trivy | Vulnérabilités HIGH/CRITICAL |
| Publication | Push vers le registre (`main`, `develop`) |
| Staging | Namespace + Secrets (Groq, Neo4j), `kustomize edit set image`, `apply -k`, attente de Neo4j et des déploiements, test de fumée |
| Production | Validation manuelle, même procédure, **rollback automatique** en cas d'échec |

Credentials : `docker-registry`, `kubeconfig-staging`, `kubeconfig-prod`, `groq-api-key`, `revisia-neo4j-password`.

---

## API

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/health` · `/api/ready` | Sondes de vie et de disponibilité |
| GET / POST | `/api/courses` | Cursus ordonné · import (`202`, analyse en tâche de fond) |
| GET / DELETE | `/api/courses/{id}` | Détail (chapitres, résumé, quiz) · suppression |
| PATCH | `/api/courses/{id}/position` | Place dans le cursus (supprime les liens devenus invalides) |
| POST | `/api/courses/{id}/relink` | Relance l'agent linker |
| GET | `/api/chapters/{id}` | Notions, compétences, prérequis, dépend de / requis par |
| GET | `/api/chapters/{id}/path` | Parcours de révision |
| GET | `/api/chapters/{id}/candidates` | Chapitres précédents candidats comme prérequis |
| POST / DELETE | `/api/dependencies` | Ajouter / retirer un lien (400 si le prérequis ne précède pas) |
| GET | `/api/graph` · `/api/graph/stats` | Graphe (filtres `course_id`, `types`) · statistiques |
| GET | `/api/concepts?name=` | Où une notion est enseignée et demandée |
| POST | `/api/chat` | Question aux agents → réponse, sources, quiz, agents, trace |

---

## Limites

- La qualité des chapitres dépend des titres du document ; sans titres, le cours est découpé par taille et le LLM nomme les parties.
- Les prérequis sont extraits par le LLM : les liens sont modifiables (retrait d'un lien dans l'onglet Chapitres).
- Le modèle d'embedding `all-MiniLM-L6-v2` est surtout entraîné sur l'anglais.
- Les PDF scannés ne sont pas lus (pas d'OCR). Pas de comptes utilisateurs.

## Perspectives

- Suivi de progression par compétence (résultats des quiz reliés aux nœuds `Skill`).
- Répétition espacée guidée par le graphe (réviser d'abord les prérequis faibles).
- Embeddings multilingues, mode 100 % local avec Ollama.

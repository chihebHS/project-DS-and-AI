# RecrutIA — Assistant RH & recrutement (MCP + IA)

## Le problème

Les recruteurs passent beaucoup de temps à jongler entre les CV stockés en local (PDF, Word), leur outil de suivi des candidats (ATS) et leurs e-mails. Il faut lire chaque CV, le comparer à la fiche de poste, puis écrire un message d'approche personnalisé à chaque candidat.

## La solution

RecrutIA est un assistant qui :

1. **centralise** les CV locaux (PDF, DOCX, TXT) dans un mini-ATS : étapes du recrutement et notes ;
2. **compare sémantiquement** les profils à une fiche de poste : présélection par embeddings, puis analyse fine par un LLM avec un score, des points forts et des manques ;
3. **rédige des messages d'approche personnalisés** (e-mail ou LinkedIn, en français ou en anglais) ;
4. propose un **assistant conversationnel** qui consulte et met à jour les données en langage naturel.

Le point central du projet est le **Model Context Protocol (MCP)** : les données RH ne sont accessibles **que** par les outils d'un serveur MCP local.

---

## Architecture

```
┌──────────────┐  HTTP  ┌────────────────────────────┐  MCP (stdio)  ┌─────────────────────────────┐
│  Frontend    │ ─────► │  Backend FastAPI           │ ────────────► │  Serveur MCP « recrutia-rh »│
│  React/Vite  │ ◄───── │  = client MCP              │ ◄──────────── │                             │
└──────────────┘        │                            │               │  13 outils :                │
                        │  ├─ matching (recruiting)  │               │  search_candidates, read_cv,│
                        │  ├─ messages d'approche    │               │  list_jobs, update_status...│
                        │  └─ agent (tool calling)   │               │                             │
                        │          │                 │               │  ├─ data/cvs/   (fichiers)  │
                        └──────────┼─────────────────┘               │  ├─ data/ats.db (SQLite)    │
                                   ▼                                 │  └─ data/chroma (embeddings)│
                         API Groq (Llama 3.3 70B)                    └─────────────────────────────┘
```

### Pourquoi MCP ?

- **Une seule porte d'entrée vers les données :** le backend et le LLM ne lisent jamais directement les fichiers ni la base. Ils ne peuvent faire que ce que les outils MCP autorisent.
- **Moindre privilège :** l'agent conversationnel n'a accès qu'à 8 outils sur 13. Il ne peut ni supprimer de candidat, ni écrire de fichier (voir `AGENT_ALLOWED_TOOLS` dans `backend/app/config.py`).
- **Réutilisable :** le serveur MCP est standard. N'importe quel client compatible MCP peut s'y connecter, pas seulement notre application.
- **Traçabilité :** chaque appel d'outil fait par l'agent est affiché dans l'interface.

### Le matching en 2 étapes

1. **Recherche sémantique** (côté serveur MCP) : chaque CV est transformé en vecteur (embedding) et stocké dans ChromaDB. La fiche de poste est aussi vectorisée, et on récupère les 5 CV les plus proches, avec un score de similarité.
2. **Analyse par le LLM** (côté backend) : les 5 CV et la fiche de poste sont envoyés au LLM en un seul appel. Il renvoie, en JSON, un score sur 100, les points forts, les manques et un résumé. Il comprend les équivalences : par exemple, « Django » montre une expérience web en Python.

### L'agent (function calling)

```
Question du recruteur
      │
      ▼
LLM + liste des outils MCP autorisés ──► « appelle search_candidates(query="NLP") »
      ▲                                              │
      │                                    backend ──► serveur MCP
      └──────────── résultat de l'outil ◄────────────┘
      (boucle, 6 étapes max, puis réponse finale)
```

---

## Technologies

| Partie | Outil |
|---|---|
| Protocole d'accès aux données | MCP (SDK Python officiel, `FastMCP`, transport stdio) |
| Backend | FastAPI |
| LLM | Llama 3.3 70B via l'API gratuite **Groq** (function calling, mode JSON) |
| Recherche sémantique | ChromaDB + embeddings `all-MiniLM-L6-v2` (calculés en local) |
| Mini-ATS | SQLite |
| Lecture des CV | pypdf, python-docx |
| Frontend | React + Vite |

---

## Structure

```
recrutia/
├── mcp_server/
│   ├── server.py        # Définition des 13 outils MCP
│   └── storage.py       # Accès aux CV, à SQLite et à ChromaDB (utilisé seulement par le serveur MCP)
├── backend/
│   ├── app/
│   │   ├── main.py      # Routes de l'API
│   │   ├── mcp_client.py# Lance le serveur MCP et appelle ses outils
│   │   ├── recruiting.py# Matching et messages d'approche
│   │   ├── agent.py     # Agent avec appel d'outils
│   │   ├── llm.py       # Appels à Groq
│   │   └── config.py
│   └── .env.example
├── frontend/src/
│   ├── App.jsx
│   └── components/      # Dashboard, Jobs, OutreachDialog, Candidates, Agent, Tools
├── exemples/
│   ├── cvs/             # 5 CV fictifs pour tester
│   └── fiche_de_poste.txt
├── requirements.txt
└── start.bat
```

---

## Installation

Prérequis : Python 3.10+, Node.js 18+ et une clé API Groq gratuite (https://console.groq.com/keys).

```bash
cd recrutia
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac : source .venv/bin/activate
pip install -r requirements.txt
copy backend\.env.example backend\.env
```

Colle ta clé dans `backend/.env`, après `GROQ_API_KEY=`.

```bash
cd frontend
npm install
```

## Lancement

**Sous Windows :** double-clique sur `start.bat`.

Ou dans deux terminaux, depuis le dossier `recrutia` :

```bash
.venv\Scripts\python -m uvicorn app.main:app --port 8002 --app-dir backend
```

```bash
cd frontend
npm run dev
```

Puis ouvre **http://localhost:5175**. Le backend démarre lui-même le serveur MCP.

> Le backend est lancé sans `--reload` : sous Windows, ce mode peut empêcher le démarrage du serveur MCP en sous-processus.

### Tester avec les exemples

1. Page **Candidats** → **Importer des CV** → sélectionne les 5 fichiers de `exemples/cvs/`.
2. Page **Postes & matching** → **Nouveau poste** → copie le contenu de `exemples/fiche_de_poste.txt`.
3. Clique sur **Trouver les meilleurs profils**, puis sur **Message d'approche**.
4. Page **Assistant** : « Trouve-moi les meilleurs profils pour un poste en NLP ».

On peut aussi déposer des CV directement dans `data/cvs/`, puis cliquer sur **Analyser le dossier des CV**.

### Utiliser le serveur MCP seul

Le serveur peut être branché sur n'importe quel client compatible MCP. Exemple de configuration :

```json
{
  "mcpServers": {
    "recrutia-rh": {
      "command": "C:/chemin/vers/recrutia/.venv/Scripts/python.exe",
      "args": ["C:/chemin/vers/recrutia/mcp_server/server.py"]
    }
  }
}
```

On peut aussi l'inspecter avec l'outil officiel : `npx @modelcontextprotocol/inspector .venv/Scripts/python mcp_server/server.py`.

---

## Confidentialité : ce qui est garanti, et ce qui ne l'est pas

- Les CV, la base et les embeddings restent **sur la machine locale**. Les embeddings sont calculés en local.
- Le LLM n'accède aux données qu'**à travers les outils MCP**, avec des droits limités.
- **Mais** quand le LLM analyse un CV, le texte de ce CV est envoyé à l'API Groq : les données sortent donc de l'entreprise. Il faut vérifier la politique de confidentialité du fournisseur (conservation, entraînement des modèles) avant un usage réel.
- Pour une confidentialité totale, il faut remplacer Groq par un LLM local (Ollama, vLLM) : voir les perspectives.

## Limites

- Le nom du candidat est déduit du nom du fichier (`Prenom_Nom.pdf`).
- Seuls 2 500 caractères par CV sont envoyés au LLM pour le matching (limite du plan gratuit Groq).
- Le modèle d'embedding est surtout entraîné sur de l'anglais.
- Les PDF scannés ne sont pas lus (pas d'OCR).
- Il n'y a ni authentification ni gestion de plusieurs recruteurs.

## Perspectives

- Un LLM local (Ollama) pour que les données ne sortent plus de l'entreprise.
- Un second serveur MCP connecté à un vrai ATS ou à Notion.
- L'envoi des e-mails via un serveur MCP de messagerie, avec validation humaine avant chaque envoi.
- Un modèle d'embedding multilingue et l'extraction automatique des compétences.
- Une évaluation du matching sur un jeu de CV annotés par des recruteurs.

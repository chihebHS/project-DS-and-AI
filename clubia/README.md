# ClubIA — Assistant pour clubs et associations étudiantes

Dans un club étudiant, les décisions se prennent en réunion, mais on oublie vite qui devait faire quoi et pour quand. ClubIA résout ce problème à l'aide de l'IA générative.

On importe le compte-rendu d'une réunion (texte collé, PDF ou **enregistrement audio**), et l'application :

1. **transcrit** l'audio en texte (Whisper) ;
2. rédige un **résumé** et liste les **décisions** prises ;
3. extrait les **tâches**, avec **qui** doit les faire et **pour quand**. Les dates relatives comme « vendredi prochain » sont converties en vraies dates ;
4. permet de **suivre l'avancement** des tâches (à faire / en cours / terminé) et signale les **retards** ;
5. répond aux **questions sur l'historique** des réunions en **citant ses sources** (RAG).

---

## Fonctionnalités

| Page | Description |
|---|---|
| Tableau de bord | Nombre de réunions et de tâches, tâches en retard, avancement global, prochaines échéances, tâches par membre |
| Nouvelle réunion | Coller un compte-rendu ou importer un fichier (PDF, TXT, MP3, WAV, M4A…) |
| Réunion | Résumé, décisions, tâches extraites (modifiables), texte complet |
| Tâches | Toutes les tâches, filtres par statut et par membre, modification du responsable, de l'échéance et du statut, ajout manuel |
| Questions | Chat sur l'historique : « Qu'a-t-on décidé pour le gala ? », « Quelles tâches sont en retard ? » |

---

## Architecture

```
┌──────────────┐    HTTP /api    ┌─────────────────────────────────┐
│  Frontend    │ ──────────────► │  Backend FastAPI (Python)       │
│  React/Vite  │ ◄────────────── │                                 │
└──────────────┘                 │  ├─ pypdf    (lecture PDF)      │
                                 │  ├─ SQLite   (réunions, tâches) │
                                 │  ├─ ChromaDB (recherche RAG)    │
                                 │  └─ Groq API                    │
                                 │      ├─ Whisper (audio → texte) │
                                 │      └─ Llama 3.3 (extraction,  │
                                 │                    réponses)    │
                                 └─────────────────────────────────┘
```

### Traitement d'un compte-rendu

```
Compte-rendu ──► Texte ──┬──► Découpage en morceaux ──► Embeddings ──► ChromaDB
 (texte/PDF/audio)       │
                         └──► LLM (JSON) ──► résumé + décisions + tâches ──► SQLite
```

L'extraction utilise le **mode JSON** du LLM : le modèle est obligé de répondre avec une structure précise (`summary`, `decisions`, `tasks[]`), ce qui permet d'enregistrer directement les tâches dans la base.

### Réponse à une question (RAG)

1. La question est transformée en vecteur, et ChromaDB renvoie les 4 passages de comptes-rendus les plus proches.
2. On y ajoute la **liste à jour des tâches** (statut, retard), car les comptes-rendus ne savent pas ce qui a été fait depuis.
3. Le LLM répond uniquement à partir de ces informations et cite les extraits utilisés `[1]`, `[2]`…

### Technologies

| Partie | Outil | Rôle |
|---|---|---|
| Frontend | React + Vite | Interface web |
| Backend | FastAPI | API REST |
| LLM | Llama 3.3 70B via **Groq** (gratuit) | Extraction, réponses |
| Transcription | Whisper large v3 turbo via Groq | Audio → texte |
| Base vectorielle | ChromaDB | Recherche sémantique |
| Base de données | SQLite | Réunions et tâches |

---

## Structure du projet

```
clubia/
├── backend/
│   ├── app/
│   │   ├── main.py              # Routes de l'API
│   │   ├── config.py            # Paramètres
│   │   ├── database.py          # Tables meetings et tasks, statistiques
│   │   └── services/
│   │       ├── documents.py     # Lecture PDF/texte + découpage
│   │       ├── transcription.py # Audio → texte (Whisper)
│   │       ├── llm.py           # Extraction résumé / décisions / tâches
│   │       └── rag.py           # Indexation, recherche, réponses citées
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/          # Dashboard, MeetingForm, MeetingView,
│                                # TaskBoard, TaskTable, ChatPanel
├── start.bat
└── README.md
```

---

## Installation

### Prérequis

- Python 3.10 ou plus récent
- Node.js 18 ou plus récent
- Une clé API Groq gratuite : https://console.groq.com/keys

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/Mac : source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Linux/Mac : cp .env.example .env
```

Ouvre `backend/.env` et colle ta clé dans `GROQ_API_KEY=`.

### 2. Frontend

```bash
cd frontend
npm install
```

## Lancement

**Sous Windows :** double-clique sur `start.bat`.

Ou dans deux terminaux :

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8001
```

```bash
cd frontend
npm run dev
```

Puis ouvre **http://localhost:5174**. La documentation de l'API est sur http://localhost:8001/docs.

> Au premier import, ChromaDB télécharge son modèle d'embedding (environ 80 Mo), une seule fois.

### Exemple de compte-rendu pour tester

```
Réunion du bureau du club Robotique. Présents : Sarah, Karim, Yasmine, Amine.
On a décidé d'organiser une journée portes ouvertes le 20 novembre.
Le budget de 300 euros a été validé.
Sarah réserve l'amphithéâtre avant vendredi prochain.
Karim prépare l'affiche et la publie sur Instagram d'ici le 10 novembre.
Yasmine contacte deux entreprises pour le sponsoring.
Amine s'occupe de la démonstration du robot.
```

---

## API

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/health` | État du serveur et de la clé Groq |
| GET | `/api/stats` | Chiffres du tableau de bord |
| GET | `/api/meetings` | Liste des réunions |
| POST | `/api/meetings` | Ajouter une réunion (`title`, `meeting_date`, `language`, `text` ou `file`) |
| GET | `/api/meetings/{id}` | Détail d'une réunion avec ses tâches |
| DELETE | `/api/meetings/{id}` | Supprimer une réunion et ses tâches |
| GET | `/api/tasks` | Liste des tâches (filtres `status`, `assignee`) |
| POST | `/api/tasks` | Ajouter une tâche à la main |
| PATCH | `/api/tasks/{id}` | Modifier une tâche (statut, responsable, échéance) |
| DELETE | `/api/tasks/{id}` | Supprimer une tâche |
| POST | `/api/chat` | Poser une question sur l'historique |

---

## Limites actuelles

- Seuls les 15 000 premiers caractères d'un compte-rendu sont analysés, à cause des limites du plan gratuit Groq.
- Les fichiers audio sont limités à 25 Mo.
- Les noms des responsables sont écrits tels que le LLM les comprend : « Karim » et « Karim B. » comptent comme deux membres différents.
- Le modèle d'embedding `all-MiniLM-L6-v2` est surtout entraîné sur de l'anglais.
- Il n'y a ni comptes utilisateurs ni gestion de plusieurs clubs.

## Perspectives

- Une liste des membres du club, pour associer automatiquement les tâches à la bonne personne.
- Des rappels par e-mail avant les échéances.
- La reconnaissance des intervenants dans l'audio (diarisation).
- La prise en charge de l'arabe, avec un modèle d'embedding multilingue.
- Un mode 100 % local avec Ollama.

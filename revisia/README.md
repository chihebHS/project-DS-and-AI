# RevisIA — Assistant de révision intelligent

Application web qui aide les étudiants à réviser leurs cours grâce à l'IA générative.

L'étudiant importe un cours (PDF, fichier texte ou **enregistrement audio**), et l'application :

1. **transcrit** l'audio en texte (Whisper) ;
2. génère un **résumé**, les **notions clés** et un **quiz** (QCM) ;
3. permet de **poser des questions** sur ses cours, avec une réponse qui **cite ses sources** (page du PDF ou minute de l'audio) grâce à un système **RAG**.

L'interface et les réponses sont disponibles en **français** et en **anglais**.

---

## Architecture

```
┌──────────────┐    HTTP /api    ┌────────────────────────────┐
│  Frontend    │ ──────────────► │  Backend FastAPI (Python)  │
│  React/Vite  │ ◄────────────── │                            │
└──────────────┘                 │  ├─ pypdf     (lecture PDF)│
                                 │  ├─ ChromaDB  (vecteurs)   │
                                 │  ├─ SQLite    (cours)      │
                                 │  └─ Groq API               │
                                 │      ├─ Whisper (audio)    │
                                 │      └─ Llama 3.3 (texte)  │
                                 └────────────────────────────┘
```

### Fonctionnement du RAG (Retrieval-Augmented Generation)

1. **Découpage** : le texte du cours est découpé en morceaux d'environ 800 caractères qui se chevauchent un peu.
2. **Embeddings** : chaque morceau est transformé en vecteur par un petit modèle local (`all-MiniLM-L6-v2`, intégré à ChromaDB), puis stocké dans ChromaDB.
3. **Recherche** : la question de l'étudiant est aussi transformée en vecteur, et on récupère les 4 morceaux les plus proches.
4. **Génération** : le LLM reçoit la question et les morceaux numérotés `[1]`, `[2]`… Il doit répondre uniquement à partir de ces extraits et les citer.

### Technologies

| Partie | Outil | Rôle |
|---|---|---|
| Frontend | React + Vite | Interface web |
| Backend | FastAPI | API REST |
| LLM | Llama 3.3 70B via **Groq** (gratuit) | Résumé, quiz, réponses |
| Transcription | Whisper large v3 turbo via Groq | Audio → texte |
| Base vectorielle | ChromaDB | Recherche sémantique |
| Base de données | SQLite | Stockage des cours |

---

## Structure du projet

```
revisia/
├── backend/
│   ├── app/
│   │   ├── main.py              # Routes de l'API
│   │   ├── config.py            # Paramètres (.env, tailles, dossiers)
│   │   ├── database.py          # Table SQLite des cours
│   │   └── services/
│   │       ├── documents.py     # Lecture PDF/texte + découpage
│   │       ├── transcription.py # Audio → texte (Whisper)
│   │       ├── llm.py           # Résumé, notions, quiz (Llama)
│   │       └── rag.py           # Indexation, recherche, réponses citées
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/          # UploadForm, CourseView, Quiz, ChatPanel
├── start.bat                    # Lance backend + frontend sous Windows
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
.venv\Scripts\activate          # Windows  (Linux/Mac : source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Linux/Mac : cp .env.example .env
```

Ouvre `backend/.env` et colle ta clé dans `GROQ_API_KEY=`.

### 2. Frontend

```bash
cd frontend
npm install
```

---

## Lancement

**Sous Windows**, il suffit de double-cliquer sur `start.bat`.

Ou, à la main, dans deux terminaux :

```bash
# Terminal 1
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2
cd frontend
npm run dev
```

Puis ouvre **http://localhost:5173**.

La documentation automatique de l'API est disponible sur http://localhost:8000/docs.

> Au premier import d'un cours, ChromaDB télécharge son modèle d'embedding (environ 80 Mo). C'est fait une seule fois.

---

## API

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/health` | État du serveur et de la clé Groq |
| GET | `/api/courses` | Liste des cours |
| POST | `/api/courses` | Importer un cours (`title`, `language`, `file`) |
| GET | `/api/courses/{id}` | Détail d'un cours (résumé, notions, quiz) |
| DELETE | `/api/courses/{id}` | Supprimer un cours |
| POST | `/api/chat` | Poser une question (`question`, `course_id`, `language`) |

---

## Limites actuelles

- Pour la génération du résumé et du quiz, seuls les 15 000 premiers caractères du cours sont envoyés au LLM, à cause des limites du plan gratuit Groq.
- Les fichiers audio sont limités à 25 Mo, la limite de l'API Whisper de Groq.
- Le modèle d'embedding `all-MiniLM-L6-v2` est surtout entraîné sur de l'anglais : la recherche est un peu moins précise en français.
- Il n'y a pas de comptes utilisateurs : l'application est prévue pour un seul utilisateur, en local.
- Les PDF scannés (images) ne sont pas lus, car il n'y a pas d'OCR.

## Perspectives

- Résumer les cours longs morceau par morceau (map-reduce) pour ne plus tronquer le texte.
- Utiliser un modèle d'embedding multilingue (ex. `paraphrase-multilingual-MiniLM-L12-v2`) et ajouter l'arabe.
- Évaluer la qualité des réponses du RAG (pertinence, fidélité aux sources).
- Ajouter des comptes utilisateurs et un suivi de progression aux quiz.
- Proposer un mode 100 % local avec Ollama pour ne pas dépendre d'une API externe.

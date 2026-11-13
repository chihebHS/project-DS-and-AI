# Projets Data Science & IA

Ce dépôt regroupe mes projets en data science et en intelligence artificielle. Chaque projet est dans son propre dossier, avec son README.

| Projet | Description | Technologies |
|---|---|---|
| [RecrutIA](recrutia/) | Assistant RH & recrutement : un serveur MCP donne accès aux CV locaux et au suivi des candidats. L'IA compare sémantiquement les profils à une fiche de poste, rédige des messages d'approche personnalisés et répond aux recruteurs grâce à un agent qui appelle les outils MCP. | Python, MCP, FastAPI, React, Groq (Llama 3.3), ChromaDB, SQLite |
| [ClubIA](clubia/) | Assistant multi-agents pour clubs étudiants : à partir d'un compte-rendu (texte, PDF ou audio), un graphe LangGraph extrait décisions et tâches ; un superviseur orchestre un agent RAG, un agent de gestion des tâches et un analyste, qui accèdent aux données via un serveur MCP. CI/CD Jenkins, Docker et Kubernetes. | Python, LangGraph, MCP, FastAPI, React, Groq (Llama 3.3, Whisper), ChromaDB, SQLite, Docker, Kubernetes, Jenkins |
| [RevisIA](revisia/) | Assistant de révision multi-agents : un graphe LangGraph découpe chaque cours en chapitres et en extrait notions, compétences à acquérir et prérequis ; un graphe de connaissances Neo4j relie chaque chapitre aux chapitres précédents dont il dépend (même cours ou cours antérieur) et calcule des parcours de révision. Agents tuteur (RAG avec sources), navigateur du graphe et examinateur, via un serveur MCP. CI/CD Jenkins, Docker et Kubernetes. | Python, LangGraph, MCP, Neo4j, FastAPI, React, d3-force, Groq (Llama 3.3, Whisper), ChromaDB, SQLite, Docker, Kubernetes, Jenkins |

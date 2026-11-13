# Projets Data Science & IA

Ce dépôt regroupe mes projets en data science et en intelligence artificielle. Chaque projet est dans son propre dossier, avec son README.

| Projet | Description | Technologies |
|---|---|---|
| [RecrutIA](recrutia/) | Assistant RH & recrutement : un serveur MCP donne accès aux CV locaux et au suivi des candidats. L'IA compare sémantiquement les profils à une fiche de poste, rédige des messages d'approche personnalisés et répond aux recruteurs grâce à un agent qui appelle les outils MCP. | Python, MCP, FastAPI, React, Groq (Llama 3.3), ChromaDB, SQLite |
| [ClubIA](clubia/) | Assistant multi-agents pour clubs étudiants : à partir d'un compte-rendu (texte, PDF ou audio), un graphe LangGraph extrait décisions et tâches ; un superviseur orchestre un agent RAG, un agent de gestion des tâches et un analyste, qui accèdent aux données via un serveur MCP. CI/CD Jenkins, Docker et Kubernetes. | Python, LangGraph, MCP, FastAPI, React, Groq (Llama 3.3, Whisper), ChromaDB, SQLite, Docker, Kubernetes, Jenkins |
| [RevisIA](revisia/) | Assistant de révision intelligent : à partir d'un cours (PDF, texte ou audio), il génère un résumé, les notions clés et un quiz, et répond aux questions en citant ses sources (RAG). | Python, FastAPI, React, Groq (Llama 3.3, Whisper), ChromaDB |

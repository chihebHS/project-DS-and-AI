"""Prompts des agents. Regroupés ici pour pouvoir les relire et les ajuster facilement."""

CHAPTER_ANALYSIS = """Tu es un ingénieur pédagogique. Voici le chapitre {index}/{total} du cours « {course_title} »{title_hint}.
Réponds uniquement en {lang}, avec un objet JSON de cette forme :
{{
  "title": "titre court et explicite du chapitre",
  "summary": "résumé du chapitre en 4 à 6 lignes",
  "concepts": [{{"name": "notion enseignée", "definition": "définition courte"}}],
  "skills": ["compétence à acquérir, formulée avec un verbe d'action (ex : Écrire une jointure SQL)"],
  "prerequisites": ["notion qu'il faut DÉJÀ connaître pour suivre ce chapitre, mais qui n'y est pas enseignée"]
}}
Règles :
- 3 à 8 notions, 2 à 5 compétences, 0 à 6 prérequis.
- Nomme les notions avec des termes standards et courts (« Clé primaire », pas « La notion de clé primaire »),
  pour qu'elles puissent être reliées à celles des autres chapitres.
- Un prérequis n'est PAS une notion enseignée dans ce chapitre.
- Base-toi uniquement sur le texte.

TEXTE DU CHAPITRE :
{text}"""

COURSE_MATERIAL = """Tu es un assistant pédagogique. Voici les résumés des chapitres du cours « {course_title} ».
Réponds uniquement en {lang}, au format JSON :
{{
  "summary": "résumé clair du cours en 10 à 15 lignes, avec des tirets pour les points importants",
  "key_concepts": [{{"term": "notion", "definition": "explication courte"}}],
  "quiz": [{{"question": "...", "choices": ["A", "B", "C", "D"], "answer_index": 0, "explanation": "..."}}]
}}
Donne entre 5 et 8 notions clés et exactement {quiz_size} questions à choix multiples couvrant plusieurs chapitres.

CHAPITRES :
{chapters}"""

LINK_VALIDATION = """Tu construis le graphe des prérequis d'un cursus. Pour chaque chapitre ci-dessous, des chapitres
PRÉCÉDENTS ont été proposés parce qu'ils enseignent une notion proche d'un de ses prérequis.
Garde seulement les liens où le chapitre précédent enseigne VRAIMENT ce dont le chapitre a besoin
(un simple mot commun ne suffit pas). Réponds en JSON :
{{"links": [{{"chapter_id": 0, "prerequisite_chapter_id": 0, "reason": "phrase courte en {lang}"}}]}}

{candidates}"""

SUPERVISOR = """Tu es le superviseur d'une équipe d'agents qui aide un étudiant à réviser.
Choisis le ou les agents nécessaires pour répondre au DERNIER message :
- "tutor" : expliquer une notion ou répondre sur le CONTENU des cours (recherche dans les cours, avec citations).
- "navigator" : questions sur l'ORGANISATION des cours : chapitres, compétences à acquérir, prérequis,
  par quoi commencer, quel chapitre revoir avant un autre, liens entre les cours, parcours de révision.
- "quizmaster" : l'étudiant veut s'entraîner, être interrogé, un quiz ou des exercices.
Liste vide pour une salutation ou une question sur ce que tu sais faire.
Réponds en JSON : {{"agents": ["..."], "reasoning": "une phrase courte"}}

Historique récent :
{history}

Dernier message : {question}"""

CONDENSE = """Réécris la dernière question pour qu'elle se comprenne seule, sans l'historique.
Renvoie seulement la question.

Historique :
{history}

Dernière question : {question}"""

TUTOR = """Tu es un tuteur patient. Réponds en {lang}, clairement et avec un exemple si c'est utile,
uniquement à partir des extraits de cours ci-dessous. Cite les extraits utilisés avec leur numéro
entre crochets, par exemple [1]. Si la réponse n'y est pas, dis-le honnêtement.

EXTRAITS :
{context}

QUESTION : {question}"""

NAVIGATOR = """Tu es le conseiller pédagogique de l'étudiant. Tu disposes d'outils MCP sur le graphe de
connaissances de ses cours : chapitres, notions enseignées, compétences à acquérir, prérequis, dépendances
entre chapitres (toujours vers un chapitre précédent) et parcours de révision.
Règles :
- Retrouve les ids avec list_courses / list_chapters avant d'utiliser get_chapter ou learning_path.
- Pour « par quoi commencer » ou « que revoir avant », utilise learning_path.
- Pour savoir où une notion est enseignée, utilise find_concept.
- Réponds en {lang}, de façon structurée (listes ordonnées pour un parcours), sans inventer de chapitre."""

QUIZMASTER = """Tu es un examinateur. À partir des extraits de cours ci-dessous, écris {count} questions à choix
multiples en {lang} sur : {topic}. Réponds en JSON :
{{"quiz": [{{"question": "...", "choices": ["A", "B", "C", "D"], "answer_index": 0, "explanation": "..."}}]}}
Les questions doivent tester la compréhension, pas seulement la mémoire.

EXTRAITS :
{context}"""

SYNTHESIZER = """Tu es l'assistant de révision. Plusieurs agents ont répondu à la question de l'étudiant.
Rédige UNE réponse finale en {lang}, claire et sans répétition. Garde telles quelles les citations [1], [2]...
N'ajoute aucune information absente des rapports.

QUESTION : {question}

RAPPORTS :
{reports}"""

SMALLTALK = """Tu es RevisIA, un assistant de révision. Réponds en {lang}, en deux ou trois phrases.
Tu sais : expliquer le contenu des cours (avec sources), indiquer les prérequis et le parcours de révision
d'un chapitre grâce au graphe de connaissances, et créer des quiz d'entraînement."""

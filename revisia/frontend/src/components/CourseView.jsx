import { useEffect, useState } from 'react'
import { deleteCourse, getChapter, getCourse, getLearningPath, moveCourse, relinkCourse, removeDependency } from '../api'
import GraphView, { LearningPath } from './GraphView'
import Quiz from './Quiz'

const TABS = [
  { id: 'summary', label: 'Résumé' },
  { id: 'chapters', label: 'Chapitres & compétences' },
  { id: 'graph', label: 'Graphe' },
  { id: 'concepts', label: 'Notions clés' },
  { id: 'quiz', label: 'Quiz' },
  { id: 'content', label: 'Texte du cours' },
]

function ChapterCard({ chapter, onChanged }) {
  const [details, setDetails] = useState(null)
  const [path, setPath] = useState(null)

  const load = () => getChapter(chapter.id).then(setDetails)
  useEffect(() => {
    load()
  }, [chapter.id])

  if (!details) return <div className="chapter muted">Chargement…</div>

  const unlink = async (prerequisiteId) => {
    if (!confirm('Retirer ce lien de dépendance ?')) return
    await removeDependency(chapter.id, prerequisiteId)
    load()
    onChanged?.()
  }

  return (
    <div className="chapter">
      <div className="chapter-head">
        <span className="chapter-num">{details.position}</span>
        <div>
          <h3>{details.title}</h3>
          {details.label && <small className="muted">{details.label}</small>}
        </div>
      </div>
      <p className="small">{details.summary}</p>
      <div className="chips-grid">
        <div>
          <h4>🎯 Compétences à acquérir</h4>
          {details.teaches.map((s) => (
            <span key={s.key} className="chip skill">
              {s.name}
            </span>
          ))}
        </div>
        <div>
          <h4>🧩 Notions</h4>
          {details.covers.map((c) => (
            <span key={c.key} className="chip concept" title={c.definition}>
              {c.name}
            </span>
          ))}
        </div>
        <div>
          <h4>📌 Prérequis</h4>
          {details.requires.length === 0 && <span className="muted small">Aucun</span>}
          {details.requires.map((c) => (
            <span key={c.key} className="chip prereq">
              {c.name}
            </span>
          ))}
        </div>
      </div>
      {details.depends_on.length > 0 && (
        <div className="deps">
          <h4>⬅ S'appuie sur (chapitres précédents)</h4>
          {details.depends_on.map((d) => (
            <div key={d.chapter_id} className="dep-row">
              <strong>{d.title}</strong> {d.reason && <span className="muted small">— {d.reason}</span>}
              <button className="icon" title="Retirer le lien" onClick={() => unlink(d.chapter_id)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {details.required_by.length > 0 && (
        <p className="small">
          ➡ Utile ensuite pour : {details.required_by.map((d) => d.title).join(', ')}
        </p>
      )}
      <button className="link" onClick={() => (path ? setPath(null) : getLearningPath(chapter.id).then(setPath))}>
        {path ? 'Masquer le parcours' : 'Parcours de révision pour ce chapitre'}
      </button>
      {path && <LearningPath path={path} />}
    </div>
  )
}

export default function CourseView({ courseId, courseCount, onDeleted, onChanged, onOpenCourse }) {
  const [course, setCourse] = useState(null)
  const [tab, setTab] = useState('summary')
  const [message, setMessage] = useState('')
  const [version, setVersion] = useState(0)

  const load = () => getCourse(courseId).then(setCourse)

  useEffect(() => {
    setCourse(null)
    setTab('summary')
    setMessage('')
    load()
  }, [courseId])

  // L'analyse tourne en tâche de fond : on interroge le backend jusqu'à ce qu'elle soit finie
  useEffect(() => {
    if (course?.status !== 'processing') return
    const timer = setTimeout(() => load().then(onChanged), 2500)
    return () => clearTimeout(timer)
  }, [course])

  if (!course) return <p className="muted">Chargement…</p>

  const remove = async () => {
    if (!confirm(`Supprimer le cours « ${course.title} » et son graphe ?`)) return
    await deleteCourse(course.id)
    onDeleted()
  }

  const move = async (delta) => {
    const result = await moveCourse(course.id, course.position + delta)
    setMessage(result.dependencies_removed ? `${result.dependencies_removed} lien(s) devenu(s) invalide(s) supprimé(s).` : '')
    await load()
    onChanged()
    setVersion((v) => v + 1)
  }

  const relink = async () => {
    setMessage('Recherche des prérequis dans les chapitres précédents…')
    try {
      const result = await relinkCourse(course.id)
      setMessage(`${result.links.length} lien(s) de dépendance trouvé(s).`)
      setVersion((v) => v + 1)
    } catch (err) {
      setMessage(err.message)
    }
  }

  return (
    <div className="card wide">
      <div className="course-header">
        <div>
          <h2>{course.title}</h2>
          <p className="muted">
            {course.filename || 'texte collé'} · {course.source_type} · cours n°{course.position} du cursus ·{' '}
            {course.chapters.length} chapitre(s)
          </p>
        </div>
        <div className="row">
          <button className="secondary" disabled={course.position <= 1} onClick={() => move(-1)} title="Placer plus tôt dans le cursus">
            ↑
          </button>
          <button className="secondary" disabled={course.position >= courseCount} onClick={() => move(1)} title="Placer plus tard dans le cursus">
            ↓
          </button>
          <button className="secondary" onClick={relink} disabled={course.status !== 'ready'}>
            Relier aux cours précédents
          </button>
          <button className="danger" onClick={remove}>
            Supprimer
          </button>
        </div>
      </div>
      {message && <p className="info">{message}</p>}
      {course.status === 'error' && <div className="alert">Erreur pendant l'analyse : {course.error}</div>}
      {course.status === 'processing' && (
        <div className="processing">
          <span className="spinner" /> Analyse par le graphe LangGraph : découpage en chapitres, notions, compétences,
          prérequis, puis recherche des liens avec les chapitres précédents…
        </div>
      )}

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? 'tab active' : 'tab'} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'summary' && <p className="pre">{course.summary || 'Pas de résumé.'}</p>}
      {tab === 'chapters' && (
        <div className="chapters" key={version}>
          {course.chapters.length === 0 && <p className="muted">Pas encore de chapitres.</p>}
          {course.chapters.map((ch) => (
            <ChapterCard key={ch.id} chapter={ch} onChanged={() => setVersion((v) => v + 1)} />
          ))}
        </div>
      )}
      {tab === 'graph' && <GraphView key={version} courseId={course.id} height={520} onOpenCourse={onOpenCourse} />}
      {tab === 'concepts' && (
        <ul className="concepts">
          {course.key_concepts.map((c, i) => (
            <li key={i}>
              <strong>{c.term}</strong> : {c.definition}
            </li>
          ))}
        </ul>
      )}
      {tab === 'quiz' && <Quiz questions={course.quiz} />}
      {tab === 'content' && <p className="pre small">{course.content}</p>}
    </div>
  )
}

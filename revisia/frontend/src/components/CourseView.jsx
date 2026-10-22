import { useEffect, useState } from 'react'
import { deleteCourse, getCourse } from '../api'
import Quiz from './Quiz'

const TABS = [
  { id: 'summary', label: 'Résumé' },
  { id: 'concepts', label: 'Notions clés' },
  { id: 'quiz', label: 'Quiz' },
  { id: 'content', label: 'Texte du cours' },
]

export default function CourseView({ courseId, onDeleted }) {
  const [course, setCourse] = useState(null)
  const [tab, setTab] = useState('summary')

  useEffect(() => {
    setCourse(null)
    setTab('summary')
    getCourse(courseId).then(setCourse)
  }, [courseId])

  if (!course) return <p className="muted">Chargement…</p>

  const remove = async () => {
    if (!confirm(`Supprimer le cours « ${course.title} » ?`)) return
    await deleteCourse(course.id)
    onDeleted()
  }

  return (
    <div className="card">
      <div className="course-header">
        <div>
          <h2>{course.title}</h2>
          <p className="muted">
            {course.filename} · {course.source_type} · ajouté le {course.created_at.replace('T', ' à ')}
          </p>
        </div>
        <button className="danger" onClick={remove}>
          Supprimer
        </button>
      </div>

      {course.status === 'error' && <div className="alert">Erreur pendant l'analyse : {course.error}</div>}

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? 'tab active' : 'tab'} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'summary' && <p className="pre">{course.summary || 'Pas de résumé.'}</p>}

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

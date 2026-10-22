import { useEffect, useState } from 'react'
import { getCourses, getHealth } from './api'
import UploadForm from './components/UploadForm'
import CourseView from './components/CourseView'
import ChatPanel from './components/ChatPanel'

export default function App() {
  const [courses, setCourses] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [page, setPage] = useState('upload') // 'upload' | 'course' | 'chat'
  const [keyMissing, setKeyMissing] = useState(false)

  const refresh = () => getCourses().then(setCourses).catch(() => {})

  useEffect(() => {
    refresh()
    getHealth().then((h) => setKeyMissing(!h.groq_key_configured)).catch(() => {})
  }, [])

  const openCourse = (id) => {
    setSelectedId(id)
    setPage('course')
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>📚 RevisIA</h1>
        <button className={page === 'upload' ? 'nav active' : 'nav'} onClick={() => setPage('upload')}>
          + Ajouter un cours
        </button>
        <button className={page === 'chat' ? 'nav active' : 'nav'} onClick={() => setPage('chat')}>
          💬 Poser une question
        </button>

        <h2>Mes cours</h2>
        {courses.length === 0 && <p className="muted">Aucun cours pour l'instant.</p>}
        {courses.map((c) => (
          <button
            key={c.id}
            className={page === 'course' && selectedId === c.id ? 'course-item active' : 'course-item'}
            onClick={() => openCourse(c.id)}
          >
            <span>{c.title}</span>
            <small>
              {c.source_type} · {c.language.toUpperCase()}
              {c.status === 'error' && ' · ⚠ erreur'}
            </small>
          </button>
        ))}
      </aside>

      <main className="content">
        {keyMissing && (
          <div className="alert">
            La clé Groq n'est pas configurée. Ajoute <code>GROQ_API_KEY</code> dans <code>backend/.env</code> puis
            relance le backend.
          </div>
        )}
        {page === 'upload' && (
          <UploadForm
            onUploaded={(course) => {
              refresh()
              openCourse(course.id)
            }}
          />
        )}
        {page === 'course' && selectedId && (
          <CourseView
            courseId={selectedId}
            onDeleted={() => {
              refresh()
              setPage('upload')
            }}
          />
        )}
        {page === 'chat' && <ChatPanel courses={courses} />}
      </main>
    </div>
  )
}

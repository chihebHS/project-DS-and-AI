import { useCallback, useEffect, useState } from 'react'
import { getCourses, getGraphStats, getHealth } from './api'
import UploadForm from './components/UploadForm'
import CourseView from './components/CourseView'
import ChatPanel from './components/ChatPanel'
import GraphView from './components/GraphView'

const STATUS_HINT = { processing: ' · ⏳ analyse…', error: ' · ⚠ erreur' }

function GraphPage({ onOpenCourse }) {
  const [stats, setStats] = useState(null)
  useEffect(() => {
    getGraphStats().then(setStats).catch(() => {})
  }, [])
  return (
    <div className="card wide">
      <h2>Graphe de connaissances du cursus</h2>
      <p className="muted small">
        Cours → chapitres → notions et compétences à acquérir. Les flèches orange <code>DEPENDS_ON</code> relient un
        chapitre aux chapitres <strong>précédents</strong> (même cours ou cours antérieur) dont il a besoin. Clique sur un
        nœud pour ses détails et son parcours de révision ; molette pour zoomer, glisser pour déplacer.
      </p>
      {stats && (
        <p className="small">
          {stats.nodes.Course} cours · {stats.nodes.Chapter} chapitres · {stats.nodes.Concept} notions ·{' '}
          {stats.nodes.Skill} compétences · {stats.edges.DEPENDS_ON} dépendances entre chapitres
        </p>
      )}
      <GraphView height={620} onOpenCourse={onOpenCourse} />
    </div>
  )
}

export default function App() {
  const [courses, setCourses] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [page, setPage] = useState('upload')
  const [health, setHealth] = useState(null)

  const refresh = useCallback(() => getCourses().then(setCourses).catch(() => {}), [])

  useEffect(() => {
    refresh()
    getHealth().then(setHealth).catch(() => setHealth({ status: 'down' }))
  }, [refresh])

  const processing = courses.some((c) => c.status === 'processing')
  useEffect(() => {
    if (!processing) return
    const timer = setInterval(refresh, 3000)
    return () => clearInterval(timer)
  }, [processing, refresh])

  const openCourse = (id) => {
    setSelectedId(id)
    setPage('course')
  }

  const nav = (id, label) => (
    <button className={page === id ? 'nav active' : 'nav'} onClick={() => setPage(id)}>
      {label}
    </button>
  )

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>📚 RevisIA</h1>
        {nav('upload', '+ Ajouter un cours')}
        {nav('graph', '🕸️ Graphe de connaissances')}
        {nav('chat', '🤖 Assistant multi-agents')}

        <h2>Mon cursus (dans l'ordre)</h2>
        {courses.length === 0 && <p className="muted">Aucun cours pour l'instant.</p>}
        {courses.map((c) => (
          <button
            key={c.id}
            className={page === 'course' && selectedId === c.id ? 'course-item active' : 'course-item'}
            onClick={() => openCourse(c.id)}
          >
            <span>
              {c.position}. {c.title}
            </span>
            <small>
              {c.chapters} chapitre(s) · {c.language.toUpperCase()}
              {STATUS_HINT[c.status] || ''}
            </small>
          </button>
        ))}

        {health?.mcp && (
          <p className="sidebar-foot">
            <span className={health.mcp.connected ? 'dot ok' : 'dot ko'} /> Serveur MCP ({health.mcp.transport}) · v
            {health.version}
          </p>
        )}
      </aside>

      <main className="content">
        {health?.status === 'down' && <div className="alert">Le backend ne répond pas (port 8000).</div>}
        {health?.status === 'ok' && !health.groq_key_configured && (
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
            courseCount={courses.length}
            onChanged={refresh}
            onOpenCourse={openCourse}
            onDeleted={() => {
              refresh()
              setPage('upload')
            }}
          />
        )}
        {page === 'graph' && <GraphPage onOpenCourse={openCourse} />}
        {page === 'chat' && <ChatPanel courses={courses} />}
      </main>
    </div>
  )
}

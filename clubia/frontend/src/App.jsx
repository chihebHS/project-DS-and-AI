import { useCallback, useEffect, useState } from 'react'
import { getHealth, getMeetings } from './api'
import Dashboard from './components/Dashboard'
import MeetingForm from './components/MeetingForm'
import MeetingView from './components/MeetingView'
import TaskBoard from './components/TaskBoard'
import ChatPanel from './components/ChatPanel'
import MembersPage from './components/MembersPage'

const PAGES = [
  { id: 'dashboard', label: '📊 Tableau de bord' },
  { id: 'new', label: '+ Nouvelle réunion' },
  { id: 'tasks', label: '✅ Tâches' },
  { id: 'members', label: '👥 Membres' },
  { id: 'chat', label: '🤖 Assistant multi-agents' },
]

const STATUS_HINT = { processing: ' · ⏳ analyse…', error: ' · ⚠ erreur' }

export default function App() {
  const [meetings, setMeetings] = useState([])
  const [page, setPage] = useState('dashboard')
  const [meetingId, setMeetingId] = useState(null)
  const [health, setHealth] = useState(null)

  const refresh = useCallback(() => getMeetings().then(setMeetings).catch(() => {}), [])

  useEffect(() => {
    refresh()
    getHealth().then(setHealth).catch(() => setHealth({ status: 'down' }))
  }, [refresh])

  // Tant qu'une réunion est en cours d'analyse, on rafraîchit la liste
  const processing = meetings.some((m) => m.status === 'processing')
  useEffect(() => {
    if (!processing) return
    const timer = setInterval(refresh, 2500)
    return () => clearInterval(timer)
  }, [processing, refresh])

  const openMeeting = (id) => {
    setMeetingId(id)
    setPage('meeting')
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>🎓 ClubIA</h1>
        {PAGES.map((p) => (
          <button key={p.id} className={page === p.id ? 'nav active' : 'nav'} onClick={() => setPage(p.id)}>
            {p.label}
          </button>
        ))}

        <h2>Réunions</h2>
        {meetings.length === 0 && <p className="muted">Aucune réunion pour l'instant.</p>}
        {meetings.map((m) => (
          <button
            key={m.id}
            className={page === 'meeting' && meetingId === m.id ? 'meeting-item active' : 'meeting-item'}
            onClick={() => openMeeting(m.id)}
          >
            <span>{m.title}</span>
            <small>
              {m.meeting_date}
              {STATUS_HINT[m.status] || ''}
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
        {health?.status === 'down' && <div className="alert">Le backend ne répond pas (port 8001).</div>}
        {health && health.status === 'ok' && !health.groq_key_configured && (
          <div className="alert">
            La clé Groq n'est pas configurée. Ajoute <code>GROQ_API_KEY</code> dans <code>backend/.env</code> puis
            relance le backend.
          </div>
        )}
        {page === 'dashboard' && <Dashboard onOpenMeeting={openMeeting} />}
        {page === 'new' && (
          <MeetingForm
            onCreated={(meeting) => {
              refresh()
              openMeeting(meeting.id)
            }}
          />
        )}
        {page === 'meeting' && meetingId && (
          <MeetingView
            meetingId={meetingId}
            onChanged={refresh}
            onDeleted={() => {
              refresh()
              setPage('dashboard')
            }}
          />
        )}
        {page === 'tasks' && <TaskBoard />}
        {page === 'members' && <MembersPage />}
        {page === 'chat' && <ChatPanel />}
      </main>
    </div>
  )
}

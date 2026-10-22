import { useEffect, useState } from 'react'
import { getHealth, getMeetings } from './api'
import Dashboard from './components/Dashboard'
import MeetingForm from './components/MeetingForm'
import MeetingView from './components/MeetingView'
import TaskBoard from './components/TaskBoard'
import ChatPanel from './components/ChatPanel'

const PAGES = [
  { id: 'dashboard', label: '📊 Tableau de bord' },
  { id: 'new', label: '+ Nouvelle réunion' },
  { id: 'tasks', label: '✅ Tâches' },
  { id: 'chat', label: '💬 Poser une question' },
]

export default function App() {
  const [meetings, setMeetings] = useState([])
  const [page, setPage] = useState('dashboard')
  const [meetingId, setMeetingId] = useState(null)
  const [keyMissing, setKeyMissing] = useState(false)

  const refresh = () => getMeetings().then(setMeetings).catch(() => {})

  useEffect(() => {
    refresh()
    getHealth().then((h) => setKeyMissing(!h.groq_key_configured)).catch(() => {})
  }, [])

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
              {m.status === 'error' && ' · ⚠ erreur'}
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
            onDeleted={() => {
              refresh()
              setPage('dashboard')
            }}
          />
        )}
        {page === 'tasks' && <TaskBoard />}
        {page === 'chat' && <ChatPanel />}
      </main>
    </div>
  )
}

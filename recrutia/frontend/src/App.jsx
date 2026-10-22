import { useEffect, useState } from 'react'
import { getHealth } from './api'
import Dashboard from './components/Dashboard'
import Jobs from './components/Jobs'
import Candidates from './components/Candidates'
import Agent from './components/Agent'
import Tools from './components/Tools'

const PAGES = [
  { id: 'dashboard', label: '📊 Tableau de bord', component: Dashboard },
  { id: 'jobs', label: '💼 Postes & matching', component: Jobs },
  { id: 'candidates', label: '👥 Candidats', component: Candidates },
  { id: 'agent', label: '🤖 Assistant', component: Agent },
  { id: 'tools', label: '🔌 Outils MCP', component: Tools },
]

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [health, setHealth] = useState(null)

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth({ status: 'down' }))
  }, [])

  const Page = PAGES.find((p) => p.id === page).component

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>RecrutIA</h1>
        <p className="tagline">Assistant RH & recrutement</p>
        {PAGES.map((p) => (
          <button key={p.id} className={page === p.id ? 'nav active' : 'nav'} onClick={() => setPage(p.id)}>
            {p.label}
          </button>
        ))}
        <div className="server-status">
          {health?.status === 'ok' ? (
            <>
              <span className="dot ok" /> Serveur MCP connecté · {health.mcp_tools} outils
            </>
          ) : (
            <>
              <span className="dot" /> Serveur MCP non joignable
            </>
          )}
        </div>
      </aside>

      <main className="content">
        {health && health.status === 'ok' && !health.groq_key_configured && (
          <div className="alert">
            La clé Groq n'est pas configurée : le matching, les messages et l'assistant ne marcheront pas. Ajoute{' '}
            <code>GROQ_API_KEY</code> dans <code>backend/.env</code> puis relance le backend.
          </div>
        )}
        <Page goTo={setPage} />
      </main>
    </div>
  )
}

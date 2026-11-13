import { useEffect, useRef, useState } from 'react'
import { askQuestion, getMcpTools } from '../api'

const EXAMPLES = [
  "Qu'est-ce qui a été décidé pour la soirée d'intégration ?",
  'Quelles tâches sont en retard ?',
  'Marque la tâche de Karim comme terminée',
  "Fais le bilan de l'avancement du club",
]

const AGENT_ICONS = { supervisor: '🧭', historian: '📚', task_manager: '🛠️', analyst: '📈', synthesizer: '✍️' }

function Trace({ steps }) {
  return (
    <details className="trace">
      <summary>Raisonnement des agents ({steps.length} étapes)</summary>
      <ol>
        {steps.map((s, i) => (
          <li key={i}>
            <strong>
              {AGENT_ICONS[s.agent]} {s.label}
            </strong>{' '}
            <span className="muted">{s.detail}</span>
            {s.tools?.length > 0 && (
              <ul>
                {s.tools.map((t, j) => (
                  <li key={j}>
                    <code>
                      {t.name}({Object.entries(t.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})
                    </code>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </details>
  )
}

export default function ChatPanel() {
  const [language, setLanguage] = useState('fr')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [threadId, setThreadId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [tools, setTools] = useState([])
  const bottom = useRef(null)

  useEffect(() => {
    getMcpTools().then(setTools).catch(() => {})
  }, [])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async (text) => {
    if (!text.trim() || loading) return
    setMessages((m) => [...m, { role: 'user', text }])
    setQuestion('')
    setLoading(true)
    try {
      const result = await askQuestion(text, language, threadId)
      setThreadId(result.thread_id)
      setMessages((m) => [
        ...m,
        { role: 'assistant', text: result.answer, sources: result.sources, trace: result.trace, agents: result.agents },
      ])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', text: `Erreur : ${err.message}`, sources: [] }])
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setMessages([])
    setThreadId(null)
  }

  return (
    <div className="card chat">
      <div className="header">
        <div>
          <h2>Assistant multi-agents</h2>
          <p className="muted small">
            Un superviseur LangGraph confie ta question à l'archiviste (RAG), au gestionnaire des tâches ou à
            l'analyste, qui accèdent aux données via le serveur MCP. La conversation est mémorisée.
          </p>
        </div>
        <div className="row">
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="fr">Réponse en français</option>
            <option value="en">Answer in English</option>
          </select>
          <button className="secondary" onClick={reset} disabled={loading || messages.length === 0}>
            Nouvelle conversation
          </button>
        </div>
      </div>

      <div className="messages">
        {messages.length === 0 && (
          <div className="examples">
            <p className="muted">Exemples :</p>
            {EXAMPLES.map((ex) => (
              <button key={ex} className="example" onClick={() => send(ex)}>
                {ex}
              </button>
            ))}
            {tools.length > 0 && (
              <details className="tools">
                <summary>{tools.length} outils MCP disponibles</summary>
                <ul>
                  {tools.map((t) => (
                    <li key={t.name}>
                      <code>{t.name}</code> {t.agent && <span className="pill">agent</span>}{' '}
                      <span className="muted">{t.description}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            {m.agents?.length > 0 && (
              <div className="agents">
                {m.agents.map((a) => (
                  <span key={a} className="pill">
                    {AGENT_ICONS[a]} {a}
                  </span>
                ))}
              </div>
            )}
            <p className="pre">{m.text}</p>
            {m.sources?.length > 0 && (
              <details>
                <summary>Sources ({m.sources.length})</summary>
                {m.sources.map((s) => (
                  <div key={s.number} className="source">
                    <strong>
                      [{s.number}] {s.title} — {s.date} ({s.label})
                    </strong>
                    {s.score != null && <span className="muted"> · pertinence {Math.round(s.score * 100)} %</span>}
                    <p>{s.excerpt}…</p>
                  </div>
                ))}
              </details>
            )}
            {m.trace?.length > 0 && <Trace steps={m.trace} />}
          </div>
        ))}
        {loading && (
          <p className="muted">
            <span className="spinner" /> Les agents travaillent…
          </p>
        )}
        <div ref={bottom} />
      </div>

      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault()
          send(question)
        }}
      >
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ta question ou ta demande…" />
        <button className="primary" disabled={loading}>
          Envoyer
        </button>
      </form>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { askQuestion, getMcpTools } from '../api'
import Quiz from './Quiz'

const EXAMPLES = [
  'Explique la différence entre une clé primaire et une clé étrangère',
  'Quels sont les prérequis du chapitre sur les jointures ?',
  'Par quoi dois-je commencer pour réviser ce cours ?',
  'Fais-moi un quiz sur les requêtes SQL',
]
const AGENT_ICONS = { supervisor: '🧭', tutor: '📚', navigator: '🕸️', quizmaster: '📝', synthesizer: '✍️' }

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

export default function ChatPanel({ courses }) {
  const [courseId, setCourseId] = useState('')
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
      const r = await askQuestion(text, courseId ? Number(courseId) : null, language, threadId)
      setThreadId(r.thread_id)
      setMessages((m) => [...m, { role: 'assistant', text: r.answer, sources: r.sources, quiz: r.quiz, trace: r.trace, agents: r.agents }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', text: `Erreur : ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card chat">
      <h2>Assistant multi-agents</h2>
      <p className="muted small">
        Un superviseur LangGraph confie ta question au tuteur (RAG sur tes cours), au navigateur (graphe des chapitres,
        compétences et prérequis) ou à l'examinateur (quiz), qui accèdent aux données via le serveur MCP. La
        conversation est mémorisée.
      </p>
      <div className="chat-options">
        <select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
          <option value="">Tous les cours</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="fr">Réponse en français</option>
          <option value="en">Answer in English</option>
        </select>
        <button className="secondary" disabled={loading || !messages.length} onClick={() => { setMessages([]); setThreadId(null) }}>
          Nouvelle conversation
        </button>
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
                      <code>{t.name}</code> {t.agent && <span className="pill">navigateur</span>}{' '}
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
            {m.quiz?.length > 0 && (
              <div className="chat-quiz">
                <Quiz questions={m.quiz} />
              </div>
            )}
            {m.sources?.length > 0 && (
              <details>
                <summary>Sources ({m.sources.length})</summary>
                {m.sources.map((s) => (
                  <div key={s.number} className="source">
                    <strong>
                      [{s.number}] {s.title} — {s.label}
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
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ta question…" />
        <button className="primary" disabled={loading}>
          Envoyer
        </button>
      </form>
    </div>
  )
}

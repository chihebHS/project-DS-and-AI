import { useState } from 'react'
import { askQuestion } from '../api'

export default function ChatPanel({ courses }) {
  const [courseId, setCourseId] = useState('')
  const [language, setLanguage] = useState('fr')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const send = async (e) => {
    e.preventDefault()
    const text = question.trim()
    if (!text) return
    setMessages((m) => [...m, { role: 'user', text }])
    setQuestion('')
    setLoading(true)
    try {
      const result = await askQuestion(text, courseId ? Number(courseId) : null, language)
      setMessages((m) => [...m, { role: 'assistant', text: result.answer, sources: result.sources }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', text: `Erreur : ${err.message}`, sources: [] }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card chat">
      <h2>Poser une question sur mes cours</h2>
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
      </div>

      <div className="messages">
        {messages.length === 0 && <p className="muted">Exemple : « Quelle est la différence entre une clé primaire et une clé étrangère ? »</p>}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <p className="pre">{m.text}</p>
            {m.sources?.length > 0 && (
              <details>
                <summary>Sources ({m.sources.length})</summary>
                {m.sources.map((s) => (
                  <div key={s.number} className="source">
                    <strong>
                      [{s.number}] {s.title} — {s.label}
                    </strong>
                    <p>{s.excerpt}…</p>
                  </div>
                ))}
              </details>
            )}
          </div>
        ))}
        {loading && <p className="muted">L'assistant réfléchit…</p>}
      </div>

      <form onSubmit={send} className="chat-form">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ta question…" />
        <button className="primary" disabled={loading}>
          Envoyer
        </button>
      </form>
    </div>
  )
}

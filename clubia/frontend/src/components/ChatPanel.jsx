import { useState } from 'react'
import { askQuestion } from '../api'

const EXAMPLES = [
  "Qu'est-ce qui a été décidé pour la soirée d'intégration ?",
  'Quelles tâches sont en retard ?',
  'Qui doit s’occuper du budget ?',
]

export default function ChatPanel() {
  const [language, setLanguage] = useState('fr')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const send = async (text) => {
    if (!text.trim() || loading) return
    setMessages((m) => [...m, { role: 'user', text }])
    setQuestion('')
    setLoading(true)
    try {
      const result = await askQuestion(text, language)
      setMessages((m) => [...m, { role: 'assistant', text: result.answer, sources: result.sources }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', text: `Erreur : ${err.message}`, sources: [] }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card chat">
      <div className="header">
        <h2>Questions sur l'historique du club</h2>
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="fr">Réponse en français</option>
          <option value="en">Answer in English</option>
        </select>
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
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <p className="pre">{m.text}</p>
            {m.sources?.length > 0 && (
              <details>
                <summary>Sources ({m.sources.length})</summary>
                {m.sources.map((s) => (
                  <div key={s.number} className="source">
                    <strong>
                      [{s.number}] {s.title} — {s.date} ({s.label})
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

import { useState } from 'react'
import { askAgent } from '../api'

const EXAMPLES = [
  'Trouve-moi les 3 meilleurs profils pour un poste de data scientist en NLP.',
  'Quels candidats connaissent Docker ? Compare leur expérience.',
  'Combien de candidats sont en entretien ?',
  'Passe Sarah Benali en présélectionné et ajoute une note : profil très solide en Python.',
]

export default function Agent() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const send = async (text) => {
    if (!text.trim() || loading) return
    const history = [...messages, { role: 'user', content: text }]
    setMessages(history)
    setInput('')
    setLoading(true)
    try {
      // On n'envoie au backend que le texte des messages (pas la trace des outils)
      const result = await askAgent(history.map(({ role, content }) => ({ role, content })))
      setMessages([...history, { role: 'assistant', content: result.answer, steps: result.steps }])
    } catch (err) {
      setMessages([...history, { role: 'assistant', content: `Erreur : ${err.message}`, steps: [] }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card chat">
      <h2 className="page-title">Assistant recrutement</h2>
      <p className="muted small">
        L'assistant choisit lui-même les outils MCP à utiliser. Chaque appel est affiché sous la réponse.
      </p>

      <div className="messages">
        {messages.length === 0 && (
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button key={ex} className="example" onClick={() => send(ex)}>
                {ex}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            {m.steps?.length > 0 && (
              <details className="steps-trace">
                <summary>🔌 {m.steps.length} appel(s) d'outils MCP</summary>
                {m.steps.map((s, j) => (
                  <div key={j} className="step">
                    <code>
                      {s.tool}({JSON.stringify(s.arguments)})
                    </code>
                    <pre>{s.result}</pre>
                  </div>
                ))}
              </details>
            )}
            <p className="pre">{m.content}</p>
          </div>
        ))}
        {loading && <p className="muted">L'assistant consulte les données via MCP…</p>}
      </div>

      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ta demande…" />
        <button className="primary" disabled={loading}>
          Envoyer
        </button>
      </form>
    </div>
  )
}

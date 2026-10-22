import { useState } from 'react'
import { writeOutreach } from '../api'

export default function OutreachDialog({ candidate, job, onClose }) {
  const [channel, setChannel] = useState('email')
  const [language, setLanguage] = useState('fr')
  const [recruiter, setRecruiter] = useState('')
  const [company, setCompany] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await writeOutreach({ candidate_id: candidate.id, job_id: job.id, channel, language, recruiter, company })
      setMessage(result.message)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const copy = async () => {
    await navigator.clipboard.writeText(message)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="header">
          <h3>
            Message pour {candidate.name} — {job.title}
          </h3>
          <button className="icon" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="row">
          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="email">E-mail</option>
            <option value="linkedin">Message LinkedIn</option>
          </select>
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="fr">Français</option>
            <option value="en">English</option>
          </select>
          <input placeholder="Ton prénom" value={recruiter} onChange={(e) => setRecruiter(e.target.value)} />
          <input placeholder="Entreprise" value={company} onChange={(e) => setCompany(e.target.value)} />
        </div>

        <button className="primary" onClick={generate} disabled={loading}>
          {loading ? 'Rédaction…' : message ? 'Régénérer' : 'Générer le message'}
        </button>
        {error && <p className="error">{error}</p>}

        {message && (
          <>
            <textarea rows={12} value={message} onChange={(e) => setMessage(e.target.value)} />
            <button onClick={copy}>{copied ? '✔ Copié' : 'Copier le message'}</button>
          </>
        )}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { createMeeting } from '../api'

const today = () => new Date().toISOString().slice(0, 10)

export default function MeetingForm({ onCreated }) {
  const [title, setTitle] = useState('')
  const [meetingDate, setMeetingDate] = useState(today())
  const [language, setLanguage] = useState('fr')
  const [mode, setMode] = useState('text') // 'text' = coller le compte-rendu, 'file' = importer
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const ready = title.trim() && (mode === 'text' ? text.trim() : file)

  const submit = async (e) => {
    e.preventDefault()
    if (!ready) return
    setLoading(true)
    setError('')
    try {
      const meeting = await createMeeting({
        title: title.trim(),
        meetingDate,
        language,
        text: mode === 'text' ? text : null,
        file: mode === 'file' ? file : null,
      })
      onCreated(meeting)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>Nouvelle réunion</h2>
      <p className="muted">
        Colle le compte-rendu ou importe un fichier (PDF, texte, enregistrement audio). L'IA en extrait le résumé, les
        décisions et les tâches avec leur responsable et leur échéance.
      </p>
      <form onSubmit={submit} className="form">
        <div className="row">
          <label>
            Titre
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex : Réunion du bureau" />
          </label>
          <label>
            Date
            <input type="date" value={meetingDate} onChange={(e) => setMeetingDate(e.target.value)} />
          </label>
          <label>
            Langue
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="fr">Français</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>

        <div className="tabs">
          <button type="button" className={mode === 'text' ? 'tab active' : 'tab'} onClick={() => setMode('text')}>
            Coller le texte
          </button>
          <button type="button" className={mode === 'file' ? 'tab active' : 'tab'} onClick={() => setMode('file')}>
            Importer un fichier
          </button>
        </div>

        {mode === 'text' ? (
          <textarea
            rows={12}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ex : Sarah s'occupe de réserver la salle pour le 15 mars. Karim prépare l'affiche avant vendredi…"
          />
        ) : (
          <input type="file" accept=".pdf,.txt,.md,.mp3,.wav,.m4a,.ogg,.webm,.flac" onChange={(e) => setFile(e.target.files[0])} />
        )}

        <button type="submit" className="primary" disabled={loading || !ready}>
          {loading ? 'Analyse en cours… (peut prendre 30 s)' : 'Analyser la réunion'}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  )
}

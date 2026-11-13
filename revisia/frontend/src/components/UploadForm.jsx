import { useState } from 'react'
import { uploadCourse } from '../api'

export default function UploadForm({ onUploaded }) {
  const [title, setTitle] = useState('')
  const [language, setLanguage] = useState('fr')
  const [mode, setMode] = useState('file')
  const [file, setFile] = useState(null)
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const ready = title.trim() && (mode === 'file' ? file : text.trim())

  const submit = async (e) => {
    e.preventDefault()
    if (!ready) return
    setLoading(true)
    setError('')
    try {
      const course = await uploadCourse({
        title: title.trim(),
        language,
        file: mode === 'file' ? file : null,
        text: mode === 'text' ? text : null,
      })
      onUploaded(course)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>Ajouter un cours</h2>
      <p className="muted">
        Importe un PDF, un fichier texte, un enregistrement audio, ou colle le texte. L'IA découpe le cours en chapitres,
        en extrait les notions, les compétences à acquérir et les prérequis, puis le relie aux chapitres des cours
        précédents dans ton cursus. Elle génère aussi un résumé et un quiz.
      </p>
      <form onSubmit={submit} className="form">
        <label>
          Titre du cours
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex : Bases de données" />
        </label>
        <label>
          Langue du cours
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="fr">Français</option>
            <option value="en">English</option>
          </select>
        </label>
        <div className="tabs">
          <button type="button" className={mode === 'file' ? 'tab active' : 'tab'} onClick={() => setMode('file')}>
            Importer un fichier
          </button>
          <button type="button" className={mode === 'text' ? 'tab active' : 'tab'} onClick={() => setMode('text')}>
            Coller le texte
          </button>
        </div>
        {mode === 'file' ? (
          <label>
            Fichier (PDF, TXT, MD, MP3, WAV, M4A)
            <input type="file" accept=".pdf,.txt,.md,.mp3,.wav,.m4a,.ogg,.webm,.flac" onChange={(e) => setFile(e.target.files[0])} />
          </label>
        ) : (
          <textarea
            rows={12}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={'Chapitre 1 : Le modèle relationnel\n...\nChapitre 2 : Les requêtes SELECT\n...'}
          />
        )}
        <p className="muted small">
          Astuce : des titres comme « Chapitre 2 », « Partie II » ou « # Titre » permettent un découpage fidèle.
        </p>
        <button type="submit" className="primary" disabled={loading || !ready}>
          {loading ? 'Envoi…' : 'Analyser le cours'}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  )
}

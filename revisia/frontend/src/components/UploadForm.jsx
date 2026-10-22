import { useState } from 'react'
import { uploadCourse } from '../api'

export default function UploadForm({ onUploaded }) {
  const [title, setTitle] = useState('')
  const [language, setLanguage] = useState('fr')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (!file || !title.trim()) return
    setLoading(true)
    setError('')
    try {
      const course = await uploadCourse(title.trim(), language, file)
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
        Importe un PDF, un fichier texte ou un enregistrement audio du cours. L'IA va générer un résumé, les notions
        clés et un quiz.
      </p>
      <form onSubmit={submit} className="form">
        <label>
          Titre du cours
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex : Bases de données - Chapitre 2" />
        </label>
        <label>
          Langue du cours
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="fr">Français</option>
            <option value="en">English</option>
          </select>
        </label>
        <label>
          Fichier (PDF, TXT, MP3, WAV, M4A)
          <input type="file" accept=".pdf,.txt,.md,.mp3,.wav,.m4a,.ogg,.webm,.flac" onChange={(e) => setFile(e.target.files[0])} />
        </label>
        <button type="submit" className="primary" disabled={loading || !file || !title.trim()}>
          {loading ? 'Analyse en cours… (peut prendre 30 s)' : 'Analyser le cours'}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  )
}

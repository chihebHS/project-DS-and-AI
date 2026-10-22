import { useEffect, useState } from 'react'
import { deleteMeeting, getMeeting } from '../api'
import TaskTable from './TaskTable'

export default function MeetingView({ meetingId, onDeleted }) {
  const [meeting, setMeeting] = useState(null)
  const [showText, setShowText] = useState(false)

  const load = () => getMeeting(meetingId).then(setMeeting)

  useEffect(() => {
    setMeeting(null)
    setShowText(false)
    load()
  }, [meetingId])

  if (!meeting) return <p className="muted">Chargement…</p>

  const remove = async () => {
    if (!confirm(`Supprimer la réunion « ${meeting.title} » et ses tâches ?`)) return
    await deleteMeeting(meeting.id)
    onDeleted()
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="header">
          <div>
            <h2>{meeting.title}</h2>
            <p className="muted">
              Réunion du {meeting.meeting_date} · source : {meeting.source_type}
            </p>
          </div>
          <button className="danger" onClick={remove}>
            Supprimer
          </button>
        </div>
        {meeting.status === 'error' && <div className="alert">Erreur pendant l'analyse : {meeting.error}</div>}

        <h3>Résumé</h3>
        <p className="pre">{meeting.summary || 'Pas de résumé.'}</p>

        <h3>Décisions</h3>
        {meeting.decisions.length === 0 ? (
          <p className="muted">Aucune décision relevée.</p>
        ) : (
          <ul>
            {meeting.decisions.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3>Tâches issues de cette réunion</h3>
        <TaskTable tasks={meeting.tasks} onChange={load} showMeeting={false} />
      </div>

      <div className="card">
        <button className="link" onClick={() => setShowText(!showText)}>
          {showText ? 'Masquer' : 'Afficher'} le compte-rendu complet
        </button>
        {showText && <p className="pre small">{meeting.content}</p>}
      </div>
    </div>
  )
}

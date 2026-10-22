import { useEffect, useState } from 'react'
import { getStats } from '../api'

export default function Dashboard({ onOpenMeeting }) {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    getStats().then(setStats).catch(() => {})
  }, [])

  if (!stats) return <p className="muted">Chargement…</p>

  const progress = stats.tasks_total ? Math.round((stats.tasks_done / stats.tasks_total) * 100) : 0

  return (
    <div className="stack">
      <div className="stats">
        <div className="stat">
          <span>{stats.meetings}</span>
          <small>réunions</small>
        </div>
        <div className="stat">
          <span>{stats.tasks_todo + stats.tasks_in_progress}</span>
          <small>tâches en attente</small>
        </div>
        <div className="stat">
          <span>{stats.tasks_done}</span>
          <small>tâches terminées</small>
        </div>
        <div className={stats.tasks_overdue ? 'stat late' : 'stat'}>
          <span>{stats.tasks_overdue}</span>
          <small>en retard</small>
        </div>
      </div>

      <div className="card">
        <h2>Avancement global : {progress} %</h2>
        <div className="bar">
          <div style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="card">
        <h2>Prochaines échéances</h2>
        {stats.upcoming.length === 0 && <p className="muted">Rien à faire pour l'instant 🎉</p>}
        <ul className="plain">
          {stats.upcoming.map((t) => (
            <li key={t.id} className={t.overdue ? 'late-text' : ''}>
              <strong>{t.due_date || 'Sans date'}</strong> — {t.description} <em>({t.assignee})</em>
              {t.meeting_id && (
                <button className="link" onClick={() => onOpenMeeting(t.meeting_id)}>
                  voir la réunion
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>Tâches par membre</h2>
        {stats.members.length === 0 && <p className="muted">Aucune tâche.</p>}
        <table>
          <thead>
            <tr>
              <th>Membre</th>
              <th>Tâches</th>
              <th>Terminées</th>
              <th>En retard</th>
            </tr>
          </thead>
          <tbody>
            {stats.members.map((m) => (
              <tr key={m.name}>
                <td>{m.name}</td>
                <td>{m.total}</td>
                <td>{m.done}</td>
                <td className={m.overdue ? 'late-text' : ''}>{m.overdue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

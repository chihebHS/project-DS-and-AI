import { useEffect, useState } from 'react'
import { getStats } from '../api'
import { STATUSES } from './status'

export default function Dashboard({ goTo }) {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    getStats().then(setStats).catch(() => {})
  }, [])

  if (!stats) return <p className="muted">Chargement…</p>

  const max = Math.max(1, ...Object.values(stats.by_status))

  return (
    <div className="stack">
      <h2 className="page-title">Tableau de bord</h2>
      <div className="stats">
        <div className="stat">
          <span>{stats.jobs}</span>
          <small>postes ouverts</small>
        </div>
        <div className="stat">
          <span>{stats.candidates}</span>
          <small>candidats</small>
        </div>
        <div className="stat">
          <span>{stats.by_status.entretien}</span>
          <small>en entretien</small>
        </div>
        <div className="stat">
          <span>{stats.by_status.embauche}</span>
          <small>embauchés</small>
        </div>
      </div>

      <div className="card">
        <h3>Pipeline de recrutement</h3>
        {Object.entries(STATUSES).map(([key, label]) => (
          <div key={key} className="pipeline-row">
            <span className="pipeline-label">{label}</span>
            <div className="pipeline-bar">
              <div className={`fill ${key}`} style={{ width: `${(stats.by_status[key] / max) * 100}%` }} />
            </div>
            <strong>{stats.by_status[key]}</strong>
          </div>
        ))}
      </div>

      <div className="card">
        <h3>Pour commencer</h3>
        <ol className="steps">
          <li>
            Importe des CV dans <button className="link" onClick={() => goTo('candidates')}>Candidats</button>.
          </li>
          <li>
            Crée une fiche de poste dans <button className="link" onClick={() => goTo('jobs')}>Postes & matching</button>,
            puis lance le matching.
          </li>
          <li>Génère un message d'approche personnalisé pour les meilleurs profils.</li>
          <li>
            Pose des questions en langage naturel à l'<button className="link" onClick={() => goTo('agent')}>Assistant</button>.
          </li>
        </ol>
      </div>
    </div>
  )
}

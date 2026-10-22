import { useEffect, useState } from 'react'
import { createJob, deleteJob, getJobs, matchCandidates } from '../api'
import OutreachDialog from './OutreachDialog'

const EMPTY_JOB = { title: '', description: '', skills: '' }

export default function Jobs() {
  const [jobs, setJobs] = useState([])
  const [form, setForm] = useState(EMPTY_JOB)
  const [showForm, setShowForm] = useState(false)
  const [selected, setSelected] = useState(null)
  const [matching, setMatching] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [outreachFor, setOutreachFor] = useState(null)

  const load = () => getJobs().then(setJobs)

  useEffect(() => {
    load()
  }, [])

  const save = async (e) => {
    e.preventDefault()
    try {
      await createJob(form)
      setForm(EMPTY_JOB)
      setShowForm(false)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const select = (job) => {
    setSelected(job)
    setMatching(null)
    setError('')
  }

  const runMatching = async () => {
    setLoading(true)
    setError('')
    try {
      setMatching(await matchCandidates(selected.id))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const remove = async (job) => {
    if (!confirm(`Supprimer le poste « ${job.title} » ?`)) return
    await deleteJob(job.id)
    if (selected?.id === job.id) setSelected(null)
    load()
  }

  return (
    <div className="stack">
      <div className="header">
        <h2 className="page-title">Postes & matching</h2>
        <button className="primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Annuler' : '+ Nouveau poste'}
        </button>
      </div>

      {showForm && (
        <form className="card form" onSubmit={save}>
          <label>
            Intitulé du poste
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Ex : Développeur Backend Python" />
          </label>
          <label>
            Description
            <textarea rows={5} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </label>
          <label>
            Compétences recherchées (séparées par des virgules)
            <input value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} placeholder="Python, FastAPI, SQL, Docker" />
          </label>
          <button className="primary">Enregistrer le poste</button>
        </form>
      )}

      <div className="two-columns">
        <div className="card list">
          {jobs.length === 0 && <p className="muted">Aucun poste. Crée ta première fiche de poste.</p>}
          {jobs.map((job) => (
            <div key={job.id} className={selected?.id === job.id ? 'list-item active' : 'list-item'} onClick={() => select(job)}>
              <strong>{job.title}</strong>
              <small>{job.skills}</small>
              <button
                className="icon"
                title="Supprimer"
                onClick={(e) => {
                  e.stopPropagation()
                  remove(job)
                }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        <div className="card">
          {!selected ? (
            <p className="muted">Sélectionne un poste pour trouver les meilleurs candidats.</p>
          ) : (
            <>
              <h3>{selected.title}</h3>
              <p className="pre small">{selected.description}</p>
              {selected.skills && (
                <div className="chips">
                  {selected.skills.split(',').map((s) => (
                    <span key={s} className="chip">
                      {s.trim()}
                    </span>
                  ))}
                </div>
              )}
              <button className="primary" onClick={runMatching} disabled={loading}>
                {loading ? 'Analyse des CV en cours…' : '🎯 Trouver les meilleurs profils'}
              </button>
              {error && <p className="error">{error}</p>}

              {matching && (
                <div className="results">
                  {matching.results.length === 0 && <p className="muted">Aucun candidat dans la base.</p>}
                  {matching.results.map((r, i) => (
                    <div key={r.id} className="result">
                      <div className="result-head">
                        <div>
                          <strong>
                            {i + 1}. {r.name}
                          </strong>
                          <small className="muted"> · {r.email || 'pas d’e-mail'}</small>
                        </div>
                        <div className={`score ${r.score >= 70 ? 'high' : r.score >= 45 ? 'mid' : 'low'}`}>{r.score}/100</div>
                      </div>
                      <p className="small">{r.summary}</p>
                      <div className="pros-cons">
                        <ul className="pros">
                          {r.strengths.map((s, j) => (
                            <li key={j}>{s}</li>
                          ))}
                        </ul>
                        <ul className="cons">
                          {r.gaps.map((g, j) => (
                            <li key={j}>{g}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="result-foot">
                        <small className="muted">Similarité sémantique : {r.similarity} %</small>
                        <button onClick={() => setOutreachFor(r)}>✉️ Message d'approche</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {outreachFor && <OutreachDialog candidate={outreachFor} job={selected} onClose={() => setOutreachFor(null)} />}
    </div>
  )
}

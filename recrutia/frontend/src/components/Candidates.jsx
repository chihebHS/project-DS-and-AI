import { useEffect, useState } from 'react'
import { addNote, deleteCandidate, getCandidate, getCandidates, importFromFolder, setStatus, uploadCvs } from '../api'
import { STATUSES } from './status'

export default function Candidates() {
  const [candidates, setCandidates] = useState([])
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState(null)
  const [note, setNote] = useState('')
  const [info, setInfo] = useState('')

  const load = () => getCandidates(filter).then(setCandidates)

  useEffect(() => {
    load()
  }, [filter])

  const open = async (id) => setSelected(await getCandidate(id))

  const upload = async (e) => {
    const files = [...e.target.files]
    if (!files.length) return
    const result = await uploadCvs(files)
    setInfo(`${result.added.length} CV importé(s).` + (result.errors.length ? ` Erreurs : ${result.errors.join(' ; ')}` : ''))
    e.target.value = ''
    load()
  }

  const scanFolder = async () => {
    const result = await importFromFolder()
    setInfo(`${result.added.length} nouveau(x) CV trouvé(s) dans le dossier.`)
    load()
  }

  const changeStatus = async (status) => {
    await setStatus(selected.id, status)
    setSelected({ ...selected, status })
    load()
  }

  const saveNote = async (e) => {
    e.preventDefault()
    if (!note.trim()) return
    const result = await addNote(selected.id, note)
    setSelected({ ...selected, notes: result.notes })
    setNote('')
  }

  const remove = async () => {
    if (!confirm(`Supprimer ${selected.name} et son CV ?`)) return
    await deleteCandidate(selected.id)
    setSelected(null)
    load()
  }

  return (
    <div className="stack">
      <div className="header">
        <h2 className="page-title">Candidats</h2>
        <div className="row">
          <button onClick={scanFolder}>📁 Analyser le dossier des CV</button>
          <label className="primary file-button">
            + Importer des CV
            <input type="file" multiple accept=".pdf,.docx,.txt" onChange={upload} hidden />
          </label>
        </div>
      </div>
      {info && <p className="info">{info}</p>}

      <div className="two-columns">
        <div className="card list">
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">Toutes les étapes</option>
            {Object.entries(STATUSES).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
          {candidates.length === 0 && <p className="muted">Aucun candidat.</p>}
          {candidates.map((c) => (
            <div key={c.id} className={selected?.id === c.id ? 'list-item active' : 'list-item'} onClick={() => open(c.id)}>
              <strong>{c.name}</strong>
              <small>
                <span className={`badge ${c.status}`}>{STATUSES[c.status]}</span> {c.filename}
              </small>
            </div>
          ))}
        </div>

        <div className="card">
          {!selected ? (
            <p className="muted">Sélectionne un candidat pour voir son CV.</p>
          ) : (
            <>
              <div className="header">
                <div>
                  <h3>{selected.name}</h3>
                  <p className="muted small">
                    {selected.email || 'pas d’e-mail'} · {selected.filename}
                  </p>
                </div>
                <button className="danger" onClick={remove}>
                  Supprimer
                </button>
              </div>

              <label className="inline">
                Étape :
                <select value={selected.status} onChange={(e) => changeStatus(e.target.value)}>
                  {Object.entries(STATUSES).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              <h4>Notes des recruteurs</h4>
              {selected.notes.length === 0 && <p className="muted small">Aucune note.</p>}
              {selected.notes.map((n, i) => (
                <p key={i} className="note">
                  <small>{n.date.replace('T', ' ')}</small> {n.text}
                </p>
              ))}
              <form className="row" onSubmit={saveNote}>
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ajouter une note…" />
                <button>Ajouter</button>
              </form>

              <h4>CV</h4>
              <p className="pre small cv">{selected.cv_text}</p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

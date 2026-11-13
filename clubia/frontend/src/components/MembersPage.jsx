import { useEffect, useState } from 'react'
import { createMember, deleteMember, getMembers, mergeMembers, updateMember } from '../api'

// Les membres servent à rattacher les noms lus par l'IA (« Karim B. ») à la bonne personne.
export default function MembersPage() {
  const [members, setMembers] = useState([])
  const [name, setName] = useState('')
  const [merge, setMerge] = useState({ keep: '', other: '' })
  const [error, setError] = useState('')

  const load = () => getMembers().then(setMembers).catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const run = async (action) => {
    setError('')
    try {
      await action()
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const add = (e) => {
    e.preventDefault()
    if (name.trim()) run(() => createMember({ name: name.trim() }).then(() => setName('')))
  }

  const editAliases = (member, value) => {
    const aliases = value.split(',').map((a) => a.trim()).filter(Boolean)
    if (aliases.join(',') !== member.aliases.join(',')) run(() => updateMember(member.id, { aliases }))
  }

  const doMerge = (e) => {
    e.preventDefault()
    if (!merge.keep || !merge.other || merge.keep === merge.other) return
    run(() => mergeMembers(Number(merge.keep), Number(merge.other)).then(() => setMerge({ keep: '', other: '' })))
  }

  return (
    <div className="stack">
      <div className="card">
        <h2>Membres du club</h2>
        <p className="muted">
          Quand l'IA extrait un responsable, son nom est rattaché à un membre connu (même prénom, alias, faute de
          frappe). Les autres façons d'écrire un nom sont gardées comme <strong>alias</strong>.
        </p>
        {error && <p className="error">{error}</p>}
        {members.length === 0 ? (
          <p className="muted">Aucun membre : ils sont créés automatiquement à l'import des réunions.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nom</th>
                <th>Alias (séparés par des virgules)</th>
                <th>E-mail</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id}>
                  <td>
                    <input
                      className="cell"
                      key={m.name}
                      defaultValue={m.name}
                      onBlur={(e) => e.target.value.trim() !== m.name && run(() => updateMember(m.id, { name: e.target.value }))}
                    />
                  </td>
                  <td>
                    <input
                      className="cell"
                      key={m.aliases.join(',')}
                      defaultValue={m.aliases.join(', ')}
                      onBlur={(e) => editAliases(m, e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="cell"
                      type="email"
                      defaultValue={m.email || ''}
                      onBlur={(e) => e.target.value !== (m.email || '') && run(() => updateMember(m.id, { email: e.target.value }))}
                    />
                  </td>
                  <td>
                    <button
                      className="icon"
                      title="Supprimer"
                      onClick={() =>
                        confirm(`Supprimer ${m.name} ? Ses tâches passeront à « Non attribué ».`) &&
                        run(() => deleteMember(m.id))
                      }
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>Ajouter un membre</h3>
        <form onSubmit={add} className="row">
          <input placeholder="Prénom Nom" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="primary">Ajouter</button>
        </form>
      </div>

      {members.length > 1 && (
        <div className="card">
          <h3>Fusionner deux fiches</h3>
          <p className="muted small">Par exemple « Karim » et « Karim Benali » : les tâches et alias sont regroupés.</p>
          <form onSubmit={doMerge} className="row">
            <select value={merge.other} onChange={(e) => setMerge({ ...merge, other: e.target.value })}>
              <option value="">Fiche à fusionner…</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
            <span>dans</span>
            <select value={merge.keep} onChange={(e) => setMerge({ ...merge, keep: e.target.value })}>
              <option value="">Fiche à garder…</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
            <button className="primary" disabled={!merge.keep || !merge.other || merge.keep === merge.other}>
              Fusionner
            </button>
          </form>
        </div>
      )}
    </div>
  )
}

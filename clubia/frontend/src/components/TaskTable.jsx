import { deleteTask, updateTask } from '../api'

export const STATUS_LABELS = { a_faire: 'À faire', en_cours: 'En cours', termine: 'Terminé' }

// Tableau des tâches : on peut changer le statut, le responsable et l'échéance directement
export default function TaskTable({ tasks, onChange, showMeeting = true }) {
  if (tasks.length === 0) return <p className="muted">Aucune tâche.</p>

  const save = async (id, changes) => {
    await updateTask(id, changes)
    onChange()
  }

  const remove = async (id) => {
    if (!confirm('Supprimer cette tâche ?')) return
    await deleteTask(id)
    onChange()
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Tâche</th>
          <th>Responsable</th>
          <th>Échéance</th>
          <th>Statut</th>
          {showMeeting && <th>Réunion</th>}
          <th></th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((t) => (
          <tr key={t.id} className={t.overdue ? 'late-row' : t.status === 'termine' ? 'done-row' : ''}>
            <td>
              {t.description}
              {t.overdue && <span className="badge">en retard</span>}
            </td>
            <td>
              <input
                className="cell"
                defaultValue={t.assignee}
                onBlur={(e) => e.target.value !== t.assignee && save(t.id, { assignee: e.target.value })}
              />
            </td>
            <td>
              <input
                className="cell"
                type="date"
                defaultValue={t.due_date || ''}
                onChange={(e) => save(t.id, { due_date: e.target.value || null })}
              />
            </td>
            <td>
              <select value={t.status} onChange={(e) => save(t.id, { status: e.target.value })}>
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </td>
            {showMeeting && <td className="small">{t.meeting_title || '—'}</td>}
            <td>
              <button className="icon" title="Supprimer" onClick={() => remove(t.id)}>
                ✕
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

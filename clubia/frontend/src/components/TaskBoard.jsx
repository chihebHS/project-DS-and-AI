import { useEffect, useState } from 'react'
import { createTask, getTasks } from '../api'
import TaskTable, { STATUS_LABELS } from './TaskTable'

export default function TaskBoard() {
  const [tasks, setTasks] = useState([])
  const [status, setStatus] = useState('')
  const [assignee, setAssignee] = useState('')
  const [newTask, setNewTask] = useState({ description: '', assignee: '', due_date: '' })

  // On charge toutes les tâches puis on filtre ici : la liste des membres reste complète
  const load = () => getTasks().then(setTasks)

  useEffect(() => {
    load()
  }, [])

  const members = [...new Set(tasks.map((t) => t.assignee))].sort()
  const visible = tasks.filter((t) => (!status || t.status === status) && (!assignee || t.assignee === assignee))

  const add = async (e) => {
    e.preventDefault()
    if (!newTask.description.trim()) return
    await createTask({
      description: newTask.description,
      assignee: newTask.assignee || 'Non attribué',
      due_date: newTask.due_date || null,
    })
    setNewTask({ description: '', assignee: '', due_date: '' })
    load()
  }

  return (
    <div className="stack">
      <div className="card">
        <h2>Suivi des tâches</h2>
        <div className="row filters">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Tous les statuts</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            <option value="">Tous les membres</option>
            {members.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <span className="muted">{visible.length} tâche(s)</span>
        </div>
        <TaskTable tasks={visible} onChange={load} />
      </div>

      <div className="card">
        <h3>Ajouter une tâche à la main</h3>
        <form onSubmit={add} className="row">
          <input
            placeholder="Description"
            value={newTask.description}
            onChange={(e) => setNewTask({ ...newTask, description: e.target.value })}
          />
          <input
            placeholder="Responsable"
            value={newTask.assignee}
            onChange={(e) => setNewTask({ ...newTask, assignee: e.target.value })}
          />
          <input type="date" value={newTask.due_date} onChange={(e) => setNewTask({ ...newTask, due_date: e.target.value })} />
          <button className="primary">Ajouter</button>
        </form>
      </div>
    </div>
  )
}

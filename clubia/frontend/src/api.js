// Fonctions pour appeler le backend FastAPI

async function handle(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || 'Erreur du serveur')
  return data
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const getHealth = () => fetch('/api/health').then(handle)
export const getStats = () => fetch('/api/stats').then(handle)

// Réunions
export const getMeetings = () => fetch('/api/meetings').then(handle)
export const getMeeting = (id) => fetch(`/api/meetings/${id}`).then(handle)
export const deleteMeeting = (id) => fetch(`/api/meetings/${id}`, { method: 'DELETE' }).then(handle)

export function createMeeting({ title, meetingDate, language, text, file }) {
  const form = new FormData()
  form.append('title', title)
  form.append('meeting_date', meetingDate)
  form.append('language', language)
  if (file) form.append('file', file)
  else form.append('text', text)
  return fetch('/api/meetings', { method: 'POST', body: form }).then(handle)
}

// Tâches
export function getTasks(filters = {}) {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.assignee) params.set('assignee', filters.assignee)
  return fetch(`/api/tasks?${params}`).then(handle)
}
export const createTask = (task) => fetch('/api/tasks', json('POST', task)).then(handle)
export const updateTask = (id, changes) => fetch(`/api/tasks/${id}`, json('PATCH', changes)).then(handle)
export const deleteTask = (id) => fetch(`/api/tasks/${id}`, { method: 'DELETE' }).then(handle)

// Questions
export const askQuestion = (question, language) => fetch('/api/chat', json('POST', { question, language })).then(handle)

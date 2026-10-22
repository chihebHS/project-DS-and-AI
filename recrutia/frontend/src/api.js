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
export const getTools = () => fetch('/api/tools').then(handle)
export const getStats = () => fetch('/api/stats').then(handle)

// Candidats
export const getCandidates = (status = '') => fetch(`/api/candidates?status=${status}`).then(handle)
export const getCandidate = (id) => fetch(`/api/candidates/${id}`).then(handle)
export const importFromFolder = () => fetch('/api/candidates/import', { method: 'POST' }).then(handle)
export const setStatus = (id, status) => fetch(`/api/candidates/${id}/status`, json('PATCH', { status })).then(handle)
export const addNote = (id, note) => fetch(`/api/candidates/${id}/notes`, json('POST', { note })).then(handle)
export const deleteCandidate = (id) => fetch(`/api/candidates/${id}`, { method: 'DELETE' }).then(handle)

export function uploadCvs(files) {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  return fetch('/api/candidates', { method: 'POST', body: form }).then(handle)
}

// Postes
export const getJobs = () => fetch('/api/jobs').then(handle)
export const createJob = (job) => fetch('/api/jobs', json('POST', job)).then(handle)
export const deleteJob = (id) => fetch(`/api/jobs/${id}`, { method: 'DELETE' }).then(handle)

// IA
export const matchCandidates = (jobId) => fetch(`/api/jobs/${jobId}/match`, { method: 'POST' }).then(handle)
export const writeOutreach = (params) => fetch('/api/outreach', json('POST', params)).then(handle)
export const askAgent = (messages) => fetch('/api/agent', json('POST', { messages })).then(handle)

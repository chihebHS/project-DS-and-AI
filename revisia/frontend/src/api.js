// Fonctions pour appeler le backend FastAPI

async function handle(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join(', ') : data.detail
    throw new Error(detail || 'Erreur du serveur')
  }
  return data
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const getHealth = () => fetch('/api/health').then(handle)
export const getMcpTools = () => fetch('/api/mcp/tools').then(handle)

// Cours
export const getCourses = () => fetch('/api/courses').then(handle)
export const getCourse = (id) => fetch(`/api/courses/${id}`).then(handle)
export const deleteCourse = (id) => fetch(`/api/courses/${id}`, { method: 'DELETE' }).then(handle)
export const moveCourse = (id, position) => fetch(`/api/courses/${id}/position`, json('PATCH', { position })).then(handle)
export const relinkCourse = (id) => fetch(`/api/courses/${id}/relink`, { method: 'POST' }).then(handle)

export function uploadCourse({ title, language, file, text }) {
  const form = new FormData()
  form.append('title', title)
  form.append('language', language)
  if (file) form.append('file', file)
  else form.append('text', text)
  return fetch('/api/courses', { method: 'POST', body: form }).then(handle)
}

// Chapitres, graphe, parcours
export const getChapter = (id) => fetch(`/api/chapters/${id}`).then(handle)
export const getLearningPath = (id) => fetch(`/api/chapters/${id}/path`).then(handle)
export const getCandidates = (id) => fetch(`/api/chapters/${id}/candidates`).then(handle)
export const addDependency = (chapterId, prerequisiteId, reason = '') =>
  fetch('/api/dependencies', json('POST', { chapter_id: chapterId, prerequisite_chapter_id: prerequisiteId, reason })).then(handle)
export const removeDependency = (chapterId, prerequisiteId) =>
  fetch(`/api/dependencies?chapter_id=${chapterId}&prerequisite_chapter_id=${prerequisiteId}`, { method: 'DELETE' }).then(handle)
export const findConcept = (name) => fetch(`/api/concepts?name=${encodeURIComponent(name)}`).then(handle)
export const getGraphStats = () => fetch('/api/graph/stats').then(handle)

export function getGraph(courseId, types = []) {
  const params = new URLSearchParams()
  if (courseId) params.set('course_id', courseId)
  types.forEach((t) => params.append('types', t))
  return fetch(`/api/graph?${params}`).then(handle)
}

// Chat multi-agents
export const askQuestion = (question, courseId, language, threadId) =>
  fetch('/api/chat', json('POST', { question, course_id: courseId, language, thread_id: threadId })).then(handle)

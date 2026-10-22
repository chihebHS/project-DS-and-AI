// Fonctions pour appeler le backend FastAPI

async function handle(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || 'Erreur du serveur')
  return data
}

export const getHealth = () => fetch('/api/health').then(handle)

export const getCourses = () => fetch('/api/courses').then(handle)

export const getCourse = (id) => fetch(`/api/courses/${id}`).then(handle)

export function uploadCourse(title, language, file) {
  const form = new FormData()
  form.append('title', title)
  form.append('language', language)
  form.append('file', file)
  return fetch('/api/courses', { method: 'POST', body: form }).then(handle)
}

export const deleteCourse = (id) => fetch(`/api/courses/${id}`, { method: 'DELETE' }).then(handle)

export function askQuestion(question, courseId, language) {
  return fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, course_id: courseId, language }),
  }).then(handle)
}

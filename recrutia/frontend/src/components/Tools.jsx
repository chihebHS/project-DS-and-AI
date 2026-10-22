import { useEffect, useState } from 'react'
import { getTools } from '../api'

export default function Tools() {
  const [tools, setTools] = useState([])

  useEffect(() => {
    getTools().then(setTools).catch(() => {})
  }, [])

  return (
    <div className="stack">
      <h2 className="page-title">Outils exposés par le serveur MCP</h2>
      <div className="card">
        <p className="small">
          Les CV et le suivi des candidats restent sur la machine de l'entreprise. Le serveur MCP est la seule porte
          d'accès à ces données : l'application et le LLM ne peuvent faire que ce que ces outils permettent.
          L'assistant n'a droit qu'aux outils marqués « Agent ».
        </p>
        <table>
          <thead>
            <tr>
              <th>Outil</th>
              <th>Description</th>
              <th>Agent</th>
            </tr>
          </thead>
          <tbody>
            {tools.map((t) => (
              <tr key={t.name}>
                <td>
                  <code>{t.name}</code>
                </td>
                <td className="small pre">{t.description}</td>
                <td>{t.agent_allowed ? '✅' : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

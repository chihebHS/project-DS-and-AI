import { useEffect, useMemo, useRef, useState } from 'react'
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force'
import { findConcept, getChapter, getGraph, getLearningPath } from '../api'

// Mêmes codes couleur que le navigateur Neo4j : un label = une couleur
export const NODE_STYLES = {
  Course: { color: '#f79767', radius: 26, label: 'Cours' },
  Chapter: { color: '#57c7e3', radius: 18, label: 'Chapitre' },
  Concept: { color: '#8dcc93', radius: 10, label: 'Notion' },
  Skill: { color: '#c990c0', radius: 10, label: 'Compétence' },
}
export const EDGE_STYLES = {
  HAS_CHAPTER: { color: '#cbd5e1', label: 'a pour chapitre' },
  NEXT: { color: '#94a3b8', label: 'chapitre suivant' },
  COVERS: { color: '#86efac', label: 'enseigne la notion' },
  TEACHES: { color: '#e9b8e0', label: 'fait acquérir' },
  REQUIRES: { color: '#fca5a5', label: 'prérequis', dash: '4 3' },
  DEPENDS_ON: { color: '#ea580c', label: 'dépend du chapitre', width: 2.5 },
}

const truncate = (text, n = 22) => (text && text.length > n ? `${text.slice(0, n - 1)}…` : text)

function Details({ node, onOpenCourse, onFocusNode }) {
  const [data, setData] = useState(null)
  const [path, setPath] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setData(null)
    setPath(null)
    setError('')
    if (node.type === 'Chapter') getChapter(node.props.chapter_id).then(setData).catch((e) => setError(e.message))
    if (node.type === 'Concept') findConcept(node.label).then(setData).catch((e) => setError(e.message))
  }, [node])

  const style = NODE_STYLES[node.type]
  return (
    <aside className="graph-details">
      <span className="node-badge" style={{ background: style.color }}>
        {style.label}
      </span>
      <h3>{node.label}</h3>
      {error && <p className="error">{error}</p>}
      {node.props.definition && <p className="small">{node.props.definition}</p>}

      {node.type === 'Course' && (
        <button className="primary small-btn" onClick={() => onOpenCourse?.(node.props.course_id)}>
          Ouvrir le cours
        </button>
      )}

      {node.type === 'Chapter' && data && (
        <>
          <p className="muted small">
            {data.course_title} · chapitre {data.position} {data.label ? `· ${data.label}` : ''}
          </p>
          <p className="small">{data.summary}</p>
          <List title="🎯 Compétences à acquérir" items={data.teaches.map((s) => s.name)} />
          <List title="🧩 Notions enseignées" items={data.covers.map((c) => c.name)} />
          <List title="📌 Prérequis" items={data.requires.map((c) => c.name)} />
          <h4>⬅ Dépend de</h4>
          {data.depends_on.length === 0 && <p className="muted small">Aucun chapitre précédent.</p>}
          {data.depends_on.map((d) => (
            <button key={d.chapter_id} className="dep" onClick={() => onFocusNode(`chapter:${d.chapter_id}`)}>
              <strong>{d.title}</strong>
              {d.reason && <small>{d.reason}</small>}
            </button>
          ))}
          <h4>➡ Requis par</h4>
          {data.required_by.length === 0 && <p className="muted small">Aucun chapitre suivant.</p>}
          {data.required_by.map((d) => (
            <button key={d.chapter_id} className="dep" onClick={() => onFocusNode(`chapter:${d.chapter_id}`)}>
              <strong>{d.title}</strong>
            </button>
          ))}
          <button className="primary small-btn" onClick={() => getLearningPath(node.props.chapter_id).then(setPath)}>
            Parcours de révision
          </button>
          {path && <LearningPath path={path} onFocusNode={onFocusNode} />}
        </>
      )}

      {node.type === 'Concept' && data && (
        <>
          <List title="Enseignée dans" items={data.taught_in.map((c) => `${c.title} (${c.course_title})`)} />
          <List title="Prérequis de" items={data.required_by.map((c) => `${c.title} (${c.course_title})`)} />
        </>
      )}
    </aside>
  )
}

function List({ title, items }) {
  if (!items.length) return null
  return (
    <>
      <h4>{title}</h4>
      <ul className="tight">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </>
  )
}

export function LearningPath({ path, onFocusNode }) {
  return (
    <ol className="path">
      {path.steps.map((s) => (
        <li key={s.chapter_id} className={s.target ? 'target' : ''}>
          <button className="link" onClick={() => onFocusNode?.(`chapter:${s.chapter_id}`)}>
            {s.title}
          </button>{' '}
          <span className="muted">({s.course_title})</span>
          {s.concepts.length > 0 && <div className="small">Notions : {s.concepts.join(', ')}</div>}
        </li>
      ))}
    </ol>
  )
}

export default function GraphView({ courseId = null, height = 560, onOpenCourse }) {
  const [types, setTypes] = useState(['Course', 'Chapter', 'Concept', 'Skill'])
  const [graph, setGraph] = useState({ nodes: [], edges: [], backend: '' })
  const [selected, setSelected] = useState(null)
  const [hovered, setHovered] = useState(null)
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const [, setTick] = useState(0)
  const [error, setError] = useState('')
  const svgRef = useRef(null)
  const simRef = useRef(null)
  const drag = useRef(null)
  const width = 900

  useEffect(() => {
    getGraph(courseId, types)
      .then((g) => {
        setError('')
        setGraph(g)
      })
      .catch((e) => setError(e.message))
  }, [courseId, types])

  // Simulation physique (d3-force) : les nœuds se repoussent, les relations agissent comme des ressorts
  const { nodes, links } = useMemo(() => {
    const previous = new Map((simRef.current?.nodes() || []).map((n) => [n.uid, n]))
    const nodes = graph.nodes.map((n) => ({ ...n, ...(previous.get(n.uid) ? { x: previous.get(n.uid).x, y: previous.get(n.uid).y } : {}) }))
    const byId = new Set(nodes.map((n) => n.uid))
    const links = graph.edges.filter((e) => byId.has(e.source) && byId.has(e.target)).map((e) => ({ ...e }))
    return { nodes, links }
  }, [graph])

  useEffect(() => {
    simRef.current?.stop()
    const sim = forceSimulation(nodes)
      .force('link', forceLink(links).id((d) => d.uid).distance((l) => (l.type === 'DEPENDS_ON' ? 140 : l.type === 'HAS_CHAPTER' ? 90 : 60)))
      .force('charge', forceManyBody().strength((d) => (d.type === 'Course' ? -900 : d.type === 'Chapter' ? -400 : -120)))
      .force('center', forceCenter(width / 2, height / 2))
      .force('x', forceX(width / 2).strength(0.03))
      .force('y', forceY(height / 2).strength(0.03))
      .force('collide', forceCollide((d) => NODE_STYLES[d.type].radius + 6))
    let frame = null
    sim.on('tick', () => {
      if (!frame) frame = requestAnimationFrame(() => { frame = null; setTick((t) => t + 1) })
    })
    simRef.current = sim
    return () => {
      sim.stop()
      if (frame) cancelAnimationFrame(frame)
    }
  }, [nodes, links, height])

  const neighbors = useMemo(() => {
    if (!hovered) return null
    const set = new Set([hovered])
    links.forEach((l) => {
      if (l.source.uid === hovered) set.add(l.target.uid)
      if (l.target.uid === hovered) set.add(l.source.uid)
    })
    return set
  }, [hovered, links])

  const toGraphCoords = (event) => {
    const rect = svgRef.current.getBoundingClientRect()
    const sx = ((event.clientX - rect.left) / rect.width) * width
    const sy = ((event.clientY - rect.top) / rect.height) * height
    return { x: (sx - view.x) / view.k, y: (sy - view.y) / view.k, sx, sy }
  }

  const onWheel = (event) => {
    event.preventDefault()
    const { sx, sy } = toGraphCoords(event)
    const k = Math.min(3, Math.max(0.3, view.k * (event.deltaY < 0 ? 1.12 : 0.89)))
    setView({ k, x: sx - ((sx - view.x) * k) / view.k, y: sy - ((sy - view.y) * k) / view.k })
  }

  useEffect(() => {
    const svg = svgRef.current
    svg?.addEventListener('wheel', onWheel, { passive: false })
    return () => svg?.removeEventListener('wheel', onWheel)
  })

  const onMouseDown = (event, node = null) => {
    event.stopPropagation()
    const p = toGraphCoords(event)
    drag.current = node ? { node, moved: false } : { pan: true, start: p, view }
    if (node) {
      node.fx = node.x
      node.fy = node.y
      simRef.current.alphaTarget(0.3).restart()
    }
  }

  const onMouseMove = (event) => {
    const d = drag.current
    if (!d) return
    const p = toGraphCoords(event)
    if (d.node) {
      d.moved = true
      d.node.fx = p.x
      d.node.fy = p.y
    } else {
      setView({ ...d.view, x: d.view.x + (p.sx - d.start.sx), y: d.view.y + (p.sy - d.start.sy) })
    }
  }

  const onMouseUp = () => {
    const d = drag.current
    drag.current = null
    if (d?.node) {
      simRef.current.alphaTarget(0)
      if (!d.moved) setSelected(d.node)
      d.node.fx = null
      d.node.fy = null
    }
  }

  const focusNode = (uid) => {
    const node = nodes.find((n) => n.uid === uid)
    if (node) {
      setSelected(node)
      setView({ k: view.k, x: width / 2 - node.x * view.k, y: height / 2 - node.y * view.k })
    }
  }

  const toggle = (type) => setTypes((t) => (t.includes(type) ? t.filter((x) => x !== type) : [...t, type]))

  return (
    <div className="graph-wrap">
      <div className="graph-toolbar">
        {Object.entries(NODE_STYLES).map(([type, s]) => (
          <label key={type} className="legend-item">
            <input type="checkbox" checked={types.includes(type)} onChange={() => toggle(type)} />
            <span className="dot" style={{ background: s.color }} /> {s.label}
          </label>
        ))}
        <span className="muted small">
          {graph.nodes.length} nœuds · {graph.edges.length} relations · moteur : {graph.backend}
        </span>
        <button className="link" onClick={() => setView({ x: 0, y: 0, k: 1 })}>
          Recentrer
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="graph-area">
        <svg
          ref={svgRef}
          className="graph-canvas"
          viewBox={`0 0 ${width} ${height}`}
          style={{ height }}
          onMouseDown={(e) => onMouseDown(e)}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
        >
          <defs>
            {Object.entries(EDGE_STYLES).map(([type, s]) => (
              <marker key={type} id={`arrow-${type}`} viewBox="0 -5 10 10" refX="10" refY="0" markerWidth="7" markerHeight="7" orient="auto">
                <path d="M0,-5L10,0L0,5" fill={s.color} />
              </marker>
            ))}
          </defs>
          {graph.nodes.length === 0 && (
            <text x={width / 2} y={height / 2} textAnchor="middle" className="empty-graph">
              Importe un cours pour construire le graphe de connaissances.
            </text>
          )}
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {links.map((l, i) => {
              if (l.source.x == null) return null
              const s = EDGE_STYLES[l.type] || EDGE_STYLES.NEXT
              const dx = l.target.x - l.source.x
              const dy = l.target.y - l.source.y
              const dist = Math.hypot(dx, dy) || 1
              const r = NODE_STYLES[l.target.type].radius + 3
              const x2 = l.target.x - (dx / dist) * r
              const y2 = l.target.y - (dy / dist) * r
              const faded = neighbors && !(neighbors.has(l.source.uid) && neighbors.has(l.target.uid))
              return (
                <g key={i} opacity={faded ? 0.12 : 1}>
                  <line
                    x1={l.source.x}
                    y1={l.source.y}
                    x2={x2}
                    y2={y2}
                    stroke={s.color}
                    strokeWidth={s.width || 1.3}
                    strokeDasharray={s.dash}
                    markerEnd={`url(#arrow-${l.type})`}
                  />
                  {neighbors && !faded && (
                    <text x={(l.source.x + x2) / 2} y={(l.source.y + y2) / 2} className="edge-label">
                      {l.type}
                    </text>
                  )}
                </g>
              )
            })}
            {nodes.map((n) => {
              if (n.x == null) return null
              const s = NODE_STYLES[n.type]
              const faded = neighbors && !neighbors.has(n.uid)
              return (
                <g
                  key={n.uid}
                  transform={`translate(${n.x},${n.y})`}
                  opacity={faded ? 0.2 : 1}
                  className="graph-node"
                  onMouseDown={(e) => onMouseDown(e, n)}
                  onMouseEnter={() => setHovered(n.uid)}
                  onMouseLeave={() => setHovered(null)}
                >
                  <circle r={s.radius} fill={s.color} stroke={selected?.uid === n.uid ? '#0f172a' : 'white'} strokeWidth={selected?.uid === n.uid ? 3 : 1.5} />
                  {n.type === 'Chapter' && (
                    <text textAnchor="middle" dy="4" className="node-inner">
                      {n.props.position}
                    </text>
                  )}
                  <text textAnchor="middle" y={s.radius + 12} className={`node-label ${n.type}`}>
                    {truncate(n.label, n.type === 'Course' ? 30 : 22)}
                  </text>
                  <title>{`${s.label} : ${n.label}`}</title>
                </g>
              )
            })}
          </g>
        </svg>
        {selected && <Details node={selected} onOpenCourse={onOpenCourse} onFocusNode={focusNode} />}
      </div>
      <div className="edge-legend">
        {Object.entries(EDGE_STYLES).map(([type, s]) => (
          <span key={type}>
            <svg width="26" height="8">
              <line x1="0" y1="4" x2="26" y2="4" stroke={s.color} strokeWidth={s.width || 2} strokeDasharray={s.dash} />
            </svg>{' '}
            <code>{type}</code> {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}

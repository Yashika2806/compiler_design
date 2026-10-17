import { useEffect, useMemo, useRef } from 'react'

// Left-to-right syntax tree drawn as SVG. Nodes appear when the parser builds ("reduces") them,
// so subtrees grow separately and are joined under their parent, like a bottom-up parse.

const CAT = {
  Program: 'prog', FunctionDef: 'func', FunctionDecl: 'func', Params: 'func', Param: 'decl',
  Declaration: 'decl', VarDecl: 'decl', InitList: 'decl', UsingDecl: 'decl', Type: 'type', Preprocessor: 'pre',
  Block: 'stmt', If: 'stmt', While: 'stmt', DoWhile: 'stmt', For: 'stmt', Switch: 'stmt', Case: 'stmt', Default: 'stmt',
  Return: 'stmt', Break: 'stmt', Continue: 'stmt', ExprStmt: 'stmt', Empty: 'stmt',
  Binary: 'expr', Unary: 'expr', Assign: 'expr', Ternary: 'expr', Call: 'expr', Index: 'expr', Member: 'expr',
  Cast: 'expr', SizeOf: 'expr', Comma: 'expr',
  Identifier: 'ident', QualifiedName: 'ident', Literal: 'lit', Error: 'err',
}
export const LEGEND = [
  ['prog', 'Program'], ['func', 'Function'], ['decl', 'Declaration'], ['type', 'Type'], ['stmt', 'Statement'],
  ['expr', 'Expression'], ['ident', 'Name'], ['lit', 'Literal'], ['err', 'Error'],
]

const ROW = 30, GAP = 46, BOX_H = 24, ROOT_GAP = 14, PAD = 16

const widthOf = (n) => Math.min(240, 24 + n.label.length * 7.3)

function computeLayout(nodes, cur) {
  const byId = {}
  nodes.forEach((n) => { byId[n.id] = n })
  const visible = nodes.filter((n) => n.step <= cur && (n.hidden_at == null || cur < n.hidden_at))
  const vis = new Set(visible.map((n) => n.id))
  const kids = (id) => byId[id].children.filter((c) => vis.has(c))
  const roots = visible
    .filter((n) => n.parent == null || !vis.has(n.parent))
    .sort((a, b) => a.tok_start - b.tok_start || a.step - b.step)

  const depthOf = {}, yOf = {}, colW = []
  let nextY = 0
  const place = (id, d) => {
    depthOf[id] = d
    colW[d] = Math.max(colW[d] || 0, widthOf(byId[id]))
    const ks = kids(id)
    if (!ks.length) { yOf[id] = nextY; nextY += ROW; return }
    ks.forEach((c) => place(c, d + 1))
    yOf[id] = (yOf[ks[0]] + yOf[ks[ks.length - 1]]) / 2
  }
  roots.forEach((r) => { place(r.id, 0); nextY += ROOT_GAP })

  const xs = [PAD]
  colW.forEach((w, d) => { xs[d + 1] = xs[d] + w + GAP })
  const pos = {}
  visible.forEach((n) => { pos[n.id] = { x: xs[depthOf[n.id]], y: yOf[n.id] + PAD, w: widthOf(n) } })
  const width = (xs[colW.length] || PAD) - GAP + PAD
  const height = Math.max(nextY + PAD * 2, 80)
  const links = []
  visible.forEach((n) => kids(n.id).forEach((c) => links.push({ from: n.id, to: c })))
  return { visible, pos, links, width: Math.max(width, 200), height, roots: roots.length }
}

function splitLabel(label) {
  const i = label.indexOf(' ')
  return i < 0 ? [label, ''] : [label.slice(0, i), label.slice(i + 1)]
}

export default function TreeView({ nodes, cur, zoom, onSelect }) {
  const boxRef = useRef(null)
  const lay = useMemo(() => computeLayout(nodes, cur), [nodes, cur])

  // scroll the newest node into view
  useEffect(() => {
    const box = boxRef.current
    const fresh = lay.visible.find((n) => n.step === cur)
    if (!box || !fresh) return
    const p = lay.pos[fresh.id]
    const x = p.x * zoom, y = p.y * zoom
    const outX = x < box.scrollLeft + 10 || x + p.w * zoom > box.scrollLeft + box.clientWidth - 10
    const outY = y < box.scrollTop + 10 || y + BOX_H > box.scrollTop + box.clientHeight - 10
    if (outX || outY) {
      box.scrollTo({
        left: outX ? Math.max(0, x - 30) : box.scrollLeft,
        top: outY ? Math.max(0, y - box.clientHeight / 2) : box.scrollTop,
        behavior: 'smooth',
      })
    }
  }, [cur, lay, zoom])

  return (
    <div className="tree-box" ref={boxRef}>
      {lay.visible.length === 0 ? (
        <p className="muted tree-empty">The tree is empty. Nodes appear here as the parser finishes each rule.</p>
      ) : (
        <svg width={lay.width * zoom} height={lay.height * zoom} viewBox={`0 0 ${lay.width} ${lay.height}`}>
          {lay.links.map((l) => {
            const a = lay.pos[l.from], b = lay.pos[l.to]
            const x1 = a.x + a.w, y1 = a.y + BOX_H / 2, x2 = b.x, y2 = b.y + BOX_H / 2
            const mx = (x1 + x2) / 2
            const d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`
            return <path key={`${l.from}-${l.to}`} d={d} style={{ d: `path("${d}")` }} className="tlink" />
          })}
          {lay.visible.map((n) => {
            const p = lay.pos[n.id]
            const [kind, rest] = splitLabel(n.label)
            const isNew = n.step === cur
            return (
              <g key={n.id} className="tnode-pos" style={{ transform: `translate(${p.x}px, ${p.y}px)` }}
                 onClick={() => onSelect && onSelect(n.step)}>
                <g className={`tnode tn-${CAT[n.kind] || 'ident'}${isNew ? ' new' : ''}`}>
                  <title>{`${n.kind} · line ${n.line}, col ${n.col}`}</title>
                  <rect width={p.w} height={BOX_H} rx="6" />
                  <text x="9" y={BOX_H / 2 + 4.5}>
                    <tspan className="tk">{kind}</tspan>
                    {rest && <tspan className="tv"> {rest.length > 28 ? rest.slice(0, 27) + '…' : rest}</tspan>}
                  </text>
                </g>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

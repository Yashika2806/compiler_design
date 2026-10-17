import { useEffect, useMemo, useRef, useState } from 'react'
import TreeView, { LEGEND } from './TreeView.jsx'
import usePlayer from './usePlayer.js'

// Phase 2: replays the parser's trace and grows the syntax tree.

const KIND_LABEL = { enter: 'TRYING A RULE', match: 'MATCH TOKEN', reduce: 'BUILD TREE NODE', error: 'SYNTAX ERROR', recover: 'ERROR RECOVERY' }

function tokText(t) {
  return t.type === 'EOF' ? 'EOF' : t.lexeme.length > 26 ? t.lexeme.slice(0, 25) + '…' : t.lexeme
}

export default function SyntaxPhase({ data, tokens }) {
  const { events, nodes, issues, stats, outline } = data
  const [showEnter, setShowEnter] = useState(true)
  const [zoom, setZoom] = useState(1)
  const lastIdx = events.length - 1
  const playable = useMemo(
    () => events.filter((e) => showEnter || e.kind !== 'enter').map((e) => e.index), [events, showEnter])
  const pl = usePlayer(playable, lastIdx, 6)
  const { cur, playing, setPlaying, setCur, speed, setSpeed, nextOf, prevOf, finished, jump } = pl

  const byId = useMemo(() => {
    const m = {}
    nodes.forEach((n) => { m[n.id] = n })
    return m
  }, [nodes])

  const ev = cur >= 0 ? events[cur] : null
  const tokenPos = ev ? ev.token_pos : 0
  const node = ev && ev.node != null ? byId[ev.node] : null
  const lookahead = tokens.find((t) => t.index === tokenPos && t.type !== 'PREPROCESSOR' && t.type !== 'ERROR')
    || tokens.find((t) => t.index >= tokenPos && t.type !== 'PREPROCESSOR' && t.type !== 'ERROR')

  // grammar rules seen so far (first appearance order)
  const rulesSoFar = useMemo(() => {
    const seen = new Set(), out = []
    for (let i = 0; i <= cur; i++) {
      const r = events[i].rule
      if (r && !seen.has(r)) { seen.add(r); out.push(r) }
    }
    return out
  }, [events, cur])
  const rulesRef = useRef(null)
  useEffect(() => {
    if (rulesRef.current) rulesRef.current.scrollTop = rulesRef.current.scrollHeight
  }, [rulesSoFar.length])

  const tokBoxRef = useRef(null)
  const nextChipRef = useRef(null)
  useEffect(() => {
    const el = nextChipRef.current, box = tokBoxRef.current
    if (!el || !box) return
    if (el.offsetTop < box.scrollTop + 4 || el.offsetTop > box.scrollTop + box.clientHeight - 36) {
      box.scrollTop = Math.max(0, el.offsetTop - 40)
    }
  }, [tokenPos])

  const jumpToIssue = (iss) => {
    const e = events.find((x) => x.kind === 'error' && x.index >= (iss.step ?? 0))
    if (e) jump(e.index)
  }

  const inRange = (t) => node && ev.kind !== 'enter' && node.tok_end >= node.tok_start
    && t.index >= node.tok_start && t.index <= node.tok_end

  return (
    <section className="lab-card" id="phase-2">
      <div className="lab-card-head">
        <span className="phase-badge on">2</span>
        <h2>Syntax Analysis</h2>
        <div className="head-stats">
          <span className="stat-chip">{stats.nodes} tree nodes</span>
          <span className="stat-chip">depth {stats.max_depth}</span>
          <span className={'stat-chip' + (stats.errors ? ' bad' : '')}>{stats.errors} syntax errors</span>
          <span className="stat-chip">backend {stats.elapsed_ms} ms</span>
        </div>
      </div>
      <p className="lab-hint">
        The parser reads the tokens from Phase 1 and checks them against the grammar of the language.
        Each time a grammar rule is completed it builds a node, children first, and joins the pieces into one tree.
        This tree is called the syntax tree (AST).
      </p>

      {stats.lexical_errors_skipped > 0 && (
        <div className="issue-box"><div className="issue warning">
          <b>note</b> {stats.lexical_errors_skipped} invalid token(s) from Phase 1 were skipped by the parser.
        </div></div>
      )}
      {issues.length > 0 && (
        <div className="issue-box">
          {issues.map((iss, i) => (
            <div key={i} className="issue error" onClick={() => jumpToIssue(iss)}>
              <b>syntax error</b> line {iss.line}, col {iss.col}: {iss.message}
            </div>
          ))}
        </div>
      )}

      <div className="controls">
        <button onClick={() => { setPlaying(false); setCur(-1) }}>⏮ Restart</button>
        <button onClick={() => { setPlaying(false); setCur(prevOf) }} disabled={cur < 0}>◀ Back</button>
        <button className="primary" onClick={() => {
          if (finished) { setCur(-1); setPlaying(true) } else setPlaying(!playing)
        }}>{playing ? '⏸ Pause' : finished ? '↻ Replay' : '▶ Play'}</button>
        <button onClick={() => { setPlaying(false); setCur(nextOf) }} disabled={finished}>Next ▶</button>
        <button onClick={() => { setPlaying(false); setCur(lastIdx) }} disabled={finished}>⏭ Skip to end</button>
        <label className="speed">Speed
          <input type="range" min="1" max="30" value={speed} onChange={(e) => setSpeed(+e.target.value)} />
          <span>{speed}/sec</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={showEnter} onChange={(e) => setShowEnter(e.target.checked)} /> show "trying a rule" steps
        </label>
      </div>
      <div className="progress"><div style={{ width: `${((cur + 1) / events.length) * 100}%` }} /></div>

      <div className="lex-grid">
        <div>
          <h3 className="sub">Input tokens</h3>
          <p className="sub-note">Dim = already consumed, dashed = the next token the parser will look at (lookahead).</p>
          <div className="tok-strip" ref={tokBoxRef}>
            {tokens.map((t) => {
              const consumed = t.index < tokenPos
              const isNext = !finished && lookahead && t.index === lookahead.index
              const cls = ['tk-chip', consumed ? 'done' : '', isNext ? 'next' : '', inRange(t) ? 'in-node' : '',
                t.type === 'ERROR' ? 'bad' : '', t.type === 'PREPROCESSOR' ? 'pre' : ''].join(' ')
              return <span key={t.index} className={cls} ref={isNext ? nextChipRef : null}>{tokText(t)}</span>
            })}
          </div>

          <h3 className="sub">Grammar rules used so far <span className="muted">({rulesSoFar.length})</span></h3>
          <div className="rules-box" ref={rulesRef}>
            {rulesSoFar.length === 0 && <span className="muted">Rules appear here as the parser uses them.</span>}
            {rulesSoFar.map((r) => (
              <div key={r} className={'rule-item' + (ev && ev.rule === r ? ' on' : '')}><code>{r}</code></div>
            ))}
          </div>
        </div>

        <div>
          <h3 className="sub">What the parser is doing{ev ? ` (step ${ev.index + 1} of ${events.length})` : ''}</h3>
          <p className="sub-note">
            Shows the grammar rule being applied, why a token is accepted, and which tree node is built from which children.
          </p>
          <div className="scan-log fast">
            {!ev && <p className="muted">Press <b>Play</b> or <b>Next</b> to start parsing from the first token.</p>}
            {ev && (
              <div key={ev.index}>
                <div className="log-top">
                  <span className={`pill pk-${ev.kind}`}>{KIND_LABEL[ev.kind]}</span>
                  {lookahead && !finished && <span className="muted">lookahead: <code className="la">{tokText(lookahead)}</code></span>}
                </div>
                {ev.rule && <div className="rule-line"><b>Rule:</b> <code className="rule-code">{ev.rule}</code></div>}
                <p className="log-msg">{ev.message}</p>
                {ev.kind === 'reduce' && node && (
                  <div className="reduce-box">
                    {node.children.length > 0 && (
                      <>
                        {node.children.map((c) => (
                          <span key={c} className="mini-node">{byId[c].label}</span>
                        ))}
                        <span className="arrow">→</span>
                      </>
                    )}
                    <span className="mini-node out">{node.label}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="tree-head">
        <h3 className="sub">Syntax tree <span className="muted">(click a node to jump to the step that built it)</span></h3>
        <div className="zoom">
          <button onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.1).toFixed(1)))}>−</button>
          <span>{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom((z) => Math.min(1.6, +(z + 0.1).toFixed(1)))}>+</button>
        </div>
      </div>
      <div className="legend">
        {LEGEND.map(([c, name]) => <span key={c} className={`leg tn-${c}`}><i />{name}</span>)}
      </div>
      <TreeView nodes={nodes} cur={cur} zoom={zoom} onSelect={jump} />

      {finished && (
        <div className="summary">
          <b>Parsing complete.</b> {stats.nodes} tree nodes, depth {stats.max_depth}, {stats.functions} function(s),
          {' '}{stats.statements} statements, {stats.expressions} expression nodes, {stats.rules_used} different grammar rules used.
          <div className="muted" style={{ marginTop: 6 }}>
            {stats.errors === 0
              ? 'The program follows the grammar, so the tree is ready for Phase 3 (semantic analysis).'
              : 'Syntax errors were reported. A real compiler stops after this phase; here the parser recovered and kept going to report as many errors as possible.'}
          </div>
          <details className="outline">
            <summary>Show the final tree as text</summary>
            <pre>{outline.map((o) => `${'  '.repeat(o.depth)}${o.text}`).join('\n')}</pre>
          </details>
        </div>
      )}
    </section>
  )
}

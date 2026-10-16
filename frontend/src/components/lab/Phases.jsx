// The 6 compiler phases, shown as a pipeline bar and (for phases not built yet) placeholder cards.

export const PHASES = [
  { n: 1, key: 'lexical',  name: 'Lexical Analysis',      short: 'source → tokens',
    soon: '' },
  { n: 2, key: 'syntax',   name: 'Syntax Analysis',       short: 'tokens → parse tree',
    soon: 'Grammar rules applied one by one while the parse tree grows on screen.' },
  { n: 3, key: 'semantic', name: 'Semantic Analysis',     short: 'meaning & types',
    soon: 'Symbol table filling up, plus type and undeclared-variable errors.' },
  { n: 4, key: 'icg',      name: 'Intermediate Code',     short: 'three-address code',
    soon: 'Three-address code generated instruction by instruction.' },
  { n: 5, key: 'optimize', name: 'Code Optimization',     short: 'faster / smaller',
    soon: 'Before vs after code with every optimization highlighted.' },
  { n: 6, key: 'codegen',  name: 'Code Generation',       short: 'target code',
    soon: 'Final pseudo-assembly produced line by line.' },
]

export function PhasePipeline({ available }) {
  const go = (n) => document.getElementById(`phase-${n}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return (
    <div className="pipeline">
      {PHASES.map((p, i) => {
        const ready = available.includes(p.key)
        return (
          <div key={p.key} className="pipe-wrap">
            <button className={'pipe-item' + (ready ? ' ready' : '')} onClick={() => go(p.n)}>
              <span className="pipe-num">{p.n}</span>
              <span className="pipe-name">{p.name}</span>
              <span className="pipe-sub">{ready ? p.short : 'coming next'}</span>
            </button>
            {i < PHASES.length - 1 && <span className="pipe-arrow">›</span>}
          </div>
        )
      })}
    </div>
  )
}

export function PhasePlaceholder({ phase }) {
  return (
    <section className="lab-card locked" id={`phase-${phase.n}`}>
      <div className="lab-card-head">
        <span className="phase-badge">{phase.n}</span>
        <h2>{phase.name}</h2>
        <span className="soon-tag">not built yet</span>
      </div>
      <p className="lab-hint">Will show: {phase.soon}</p>
    </section>
  )
}

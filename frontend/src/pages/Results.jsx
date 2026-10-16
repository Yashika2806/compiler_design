import { useState } from 'react'
import { useLocation, Navigate, Link } from 'react-router-dom'
import ScoreGauge from '../components/ScoreGauge.jsx'
import SeverityBadge from '../components/SeverityBadge.jsx'
import SourceViewer from '../components/SourceViewer.jsx'

export default function Results() {
  const { state } = useLocation()
  const [activeLine, setActiveLine] = useState(null)
  const [expandedId, setExpandedId] = useState(null)

  if (!state?.report) {
    return <Navigate to="/analyze" replace />
  }

  const { report, source } = state
  const findings = report.detailed_findings

  return (
    <div className="main">
      <h1>Analysis Results</h1>
      <p className="subtitle">{report.contract_name} &middot; Solidity {report.solidity_version} &middot; {report.analysis_date}</p>

      <div className="grid grid-2" style={{ marginBottom: 20, alignItems: 'stretch' }}>
        <div className="card" style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
          <ScoreGauge score={report.security_score} riskLevel={report.risk_level} />
          <div>
            <div className="stat-label">Risk Level</div>
            <div className={`stat-value risk-${report.risk_level}`}>{report.risk_level}</div>
            <p style={{ color: 'var(--text-dim)', fontSize: 13, marginTop: 8 }}>{report.executive_summary}</p>
          </div>
        </div>

        <div className="card">
          <h2>Severity Breakdown</h2>
          {Object.entries(report.vulnerability_summary.by_severity).map(([sev, count]) => (
            <div key={sev} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
              <SeverityBadge severity={sev} />
              <span style={{ fontWeight: 600 }}>{count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-2" style={{ alignItems: 'start' }}>
        <div className="card">
          <h2>Findings ({findings.length})</h2>
          {findings.length === 0 && <div className="empty-state">No issues detected by the current rule set.</div>}
          {findings.map((f, i) => (
            <div
              key={i}
              className="finding-card"
              onClick={() => { setActiveLine(f.line); setExpandedId(expandedId === i ? null : i) }}
            >
              <SeverityBadge severity={f.severity} />
              <div className="finding-title">{f.title}</div>
              <div className="finding-meta">
                {f.function_name}() &middot; line {f.line} &middot; confidence: {f.confidence} &middot; {f.rule_id}
              </div>
              {expandedId === i && (
                <>
                  <div className="finding-section">
                    <div className="finding-section-label">Vulnerable code</div>
                    <div className="finding-snippet">{f.code_snippet}</div>
                  </div>
                  <div className="finding-section">
                    <div className="finding-section-label">Explanation</div>
                    <div>{f.explanation}</div>
                  </div>
                  <div className="finding-section">
                    <div className="finding-section-label">Security impact</div>
                    <div>{f.security_impact}</div>
                  </div>
                  <div className="finding-section">
                    <div className="finding-section-label">Recommended fix</div>
                    <div>{f.recommendation}</div>
                  </div>
                  {f.secure_example && (
                    <div className="finding-section">
                      <div className="finding-section-label">Secure example</div>
                      <div className="finding-snippet">{f.secure_example}</div>
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>

        <div className="card">
          <h2>Source Code</h2>
          <SourceViewer source={source} findings={findings} activeLine={activeLine} />
        </div>
      </div>

      <div className="card">
        <h2>Recommendations</h2>
        {report.recommendations.length === 0 && <div className="empty-state">No specific recommendations — no issues found.</div>}
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {report.recommendations.map((r, i) => (
            <li key={i} style={{ marginBottom: 8 }}><strong>{r.related_to}:</strong> {r.recommendation}</li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>Final Assessment</h2>
        <p style={{ margin: 0 }}>{report.final_assessment}</p>
        <p style={{ color: 'var(--text-dim)', fontSize: 12.5, marginTop: 14, marginBottom: 0 }}>
          <strong>Limitations:</strong> {report.limitations}
        </p>
      </div>

      <Link to="/analyze"><button className="secondary">Analyze another contract</button></Link>
    </div>
  )
}

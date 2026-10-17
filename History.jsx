import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchHistory } from '../api.js'
import SeverityBadge from '../components/SeverityBadge.jsx'

export default function History() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchHistory()
      .then(setHistory)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="main">
      <h1>Analysis History</h1>
      <p className="subtitle">All previous smart contract scans, saved to the local database.</p>

      {error && <div className="error-box">Couldn't reach the backend: {error}</div>}

      <div className="card">
        {loading && <div className="empty-state">Loading…</div>}
        {!loading && history.length === 0 && <div className="empty-state">No analyses yet.</div>}
        {history.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Contract</th>
                <th>Score</th>
                <th>Risk</th>
                <th>Findings</th>
                <th>Critical</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id}>
                  <td><Link to={`/history/${h.id}`}>{h.contract_name}</Link></td>
                  <td>{h.security_score}/100</td>
                  <td><SeverityBadge severity={h.risk_level} /></td>
                  <td>{h.total_findings}</td>
                  <td>{h.severity_counts?.Critical || 0}</td>
                  <td>{new Date(h.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const COLOR_BY_RISK = {
  Low: '#0d9467',
  Medium: '#d4a017',
  High: '#e0700f',
  Critical: '#d92d3f',
}

export default function ScoreGauge({ score, riskLevel, size = 120 }) {
  const radius = (size - 14) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - score / 100)
  const color = COLOR_BY_RISK[riskLevel] || '#5a6679'

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={radius} stroke="#e2e7ef" strokeWidth="10" fill="none" />
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        stroke={color} strokeWidth="10" fill="none"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 0.6s ease' }}
      />
      <text x="50%" y="46%" textAnchor="middle" fill="#1a2233" fontSize="26" fontWeight="700">{score}</text>
      <text x="50%" y="64%" textAnchor="middle" fill="#5a6679" fontSize="11">/ 100</text>
    </svg>
  )
}

const COLOR_BY_RISK = {
  Low: '#3ecf8e',
  Medium: '#ffd43b',
  High: '#ff9f43',
  Critical: '#ff4d5e',
}

export default function ScoreGauge({ score, riskLevel, size = 120 }) {
  const radius = (size - 14) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - score / 100)
  const color = COLOR_BY_RISK[riskLevel] || '#8fa0b5'

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={radius} stroke="#263041" strokeWidth="10" fill="none" />
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        stroke={color} strokeWidth="10" fill="none"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 0.6s ease' }}
      />
      <text x="50%" y="46%" textAnchor="middle" fill="#e6ecf3" fontSize="26" fontWeight="700">{score}</text>
      <text x="50%" y="64%" textAnchor="middle" fill="#8fa0b5" fontSize="11">/ 100</text>
    </svg>
  )
}

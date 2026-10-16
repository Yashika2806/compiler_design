export default function SeverityBadge({ severity }) {
  return <span className={`badge badge-${severity}`}>{severity}</span>
}

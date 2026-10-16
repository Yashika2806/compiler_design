import { NavLink } from 'react-router-dom'

export default function Sidebar() {
  const linkClass = ({ isActive }) => 'nav-link' + (isActive ? ' active' : '')
  return (
    <div className="sidebar">
      <div className="brand">Vuln<span>Detect</span><br />Smart Contract Security</div>
      <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
      <NavLink to="/lab" className={linkClass}>Compiler Lab</NavLink>
      <NavLink to="/analyze" className={linkClass}>Analyze Contract</NavLink>
      <NavLink to="/history" className={linkClass}>Analysis History</NavLink>
    </div>
  )
}

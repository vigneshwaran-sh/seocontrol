import { Routes, Route } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Users from './pages/Users'
import SpaceTasks from './pages/SpaceTasks'
import SpaceDocs from './pages/SpaceDocs'
import SpaceAgents from './pages/SpaceAgents'
import AgentDetail from './pages/AgentDetail'
import DocEditor from './pages/DocEditor'
import Settings from './pages/Settings'
import LLMLogs from './pages/LLMLogs'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import RoleGate from './components/RoleGate'

function App() {
  return (
    <Routes>
      {/* Public route */}
      <Route path="/login" element={<Login />} />

      {/* Protected routes with sidebar layout */}
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route
            path="/users"
            element={
              <RoleGate requiredRole="admin">
                <Users />
              </RoleGate>
            }
          />
          <Route
            path="/settings"
            element={
              <RoleGate requiredRole="admin">
                <Settings />
              </RoleGate>
            }
          />
          <Route path="/spaces/:spaceId/tasks" element={<SpaceTasks />} />
          <Route path="/spaces/:spaceId/docs" element={<SpaceDocs />} />
          <Route path="/spaces/:spaceId/docs/:docId" element={<DocEditor />} />
          <Route path="/spaces/:spaceId/agents" element={<SpaceAgents />} />
          <Route path="/spaces/:spaceId/agents/:agentId" element={<AgentDetail />} />
          <Route path="/spaces/:spaceId/logs" element={<LLMLogs />} />
        </Route>
      </Route>
    </Routes>
  )
}

export default App

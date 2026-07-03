import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing.jsx'
import { Login, Signup } from './pages/Auth.jsx'
import Dashboard from './pages/Dashboard.jsx'
import ApiKeys from './pages/ApiKeys.jsx'
import Playground from './pages/Playground.jsx'
import { AuditLog } from './pages/Stub.jsx'
import Layout from './components/Layout.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/playground" element={<Playground />} />
          <Route path="/api-keys" element={<ApiKeys />} />
          <Route path="/audit" element={<AuditLog />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)

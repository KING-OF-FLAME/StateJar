import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing.jsx'
import { Login, Signup } from './pages/Auth.jsx'
import Layout from './components/Layout.jsx'
import './index.css'

// Console pages load on demand. A landing visitor used to download the whole
// console — Playground included — before anything could paint, which put ~2/3
// of the JS on the critical path of the page Lighthouse actually measures.
const Dashboard = lazy(() => import('./pages/Dashboard.jsx'))
const Playground = lazy(() => import('./pages/Playground.jsx'))
const ApiKeys = lazy(() => import('./pages/ApiKeys.jsx'))
const ApiDocs = lazy(() => import('./pages/ApiDocs.jsx'))
const AuditLog = lazy(() => import('./pages/AuditLog.jsx'))
const About = lazy(() => import('./pages/About.jsx'))
const Help = lazy(() => import('./pages/Help.jsx'))
const Profile = lazy(() => import('./pages/Profile.jsx'))

const Loading = () => <p className="empty-note">Loading…</p>

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Suspense fallback={<Loading />}><Dashboard /></Suspense>} />
          <Route path="/playground" element={<Suspense fallback={<Loading />}><Playground /></Suspense>} />
          <Route path="/api-keys" element={<Suspense fallback={<Loading />}><ApiKeys /></Suspense>} />
          <Route path="/api-docs" element={<Suspense fallback={<Loading />}><ApiDocs /></Suspense>} />
          <Route path="/audit" element={<Suspense fallback={<Loading />}><AuditLog /></Suspense>} />
          <Route path="/about" element={<Suspense fallback={<Loading />}><About /></Suspense>} />
          <Route path="/help" element={<Suspense fallback={<Loading />}><Help /></Suspense>} />
          <Route path="/profile" element={<Suspense fallback={<Loading />}><Profile /></Suspense>} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)

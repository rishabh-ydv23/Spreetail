import React from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import Login from './pages/Login'
import ImportPage from './pages/ImportPage'

export default function App() {
  return (
    <div className="app">
      <nav>
        <Link to="/">Home</Link> | <Link to="/imports">Imports</Link>
      </nav>
      <Routes>
        <Route path="/" element={<div>Welcome to Spreetail</div>} />
        <Route path="/login" element={<Login />} />
        <Route path="/imports" element={<ImportPage />} />
      </Routes>
    </div>
  )
}

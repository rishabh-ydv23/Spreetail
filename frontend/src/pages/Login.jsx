import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, setAuthToken } from '../api'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const nav = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    try {
      const data = await login(email, password)
      setAuthToken(data.token)
      localStorage.setItem('authToken', data.token)
      nav('/imports')
    } catch (err) {
      setError(err?.response?.data || 'Login failed')
    }
  }

  return (
    <div className="login">
      <h2>Login</h2>
      <form onSubmit={handleSubmit}>
        <div>
          <label>Email</label>
          <input value={email} onChange={e=>setEmail(e.target.value)} />
        </div>
        <div>
          <label>Password</label>
          <input type="password" value={password} onChange={e=>setPassword(e.target.value)} />
        </div>
        <button type="submit">Login</button>
      </form>
      {error && <pre className="error">{JSON.stringify(error)}</pre>}
    </div>
  )
}

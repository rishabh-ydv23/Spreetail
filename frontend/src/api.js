import axios from 'axios'

const API = axios.create({ baseURL: '/api/v1' })

export function setAuthToken(token) {
  if (token) API.defaults.headers.common['Authorization'] = `Token ${token}`
  else delete API.defaults.headers.common['Authorization']
}

export async function login(email, password) {
  const resp = await API.post('/auth/login/', { email, password })
  return resp.data
}

export async function uploadImport(groupId, file) {
  const fd = new FormData()
  fd.append('file', file)
  const resp = await API.post(`/groups/${groupId}/imports/`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  return resp.data
}

export async function getBatch(groupId, batchId) {
  const resp = await API.get(`/groups/${groupId}/imports/${batchId}/`)
  return resp.data
}

export async function commitBatch(groupId, batchId, approveAll=false) {
  const resp = await API.post(`/groups/${groupId}/imports/${batchId}/commit/`, { approve_all: approveAll })
  return resp.data
}

export async function getIssues(groupId, batchId) {
  const resp = await API.get(`/groups/${groupId}/imports/${batchId}/issues/`)
  return resp.data
}

export async function resolveIssue(groupId, batchId, issueId) {
  const resp = await API.post(`/groups/${groupId}/imports/${batchId}/issues/${issueId}/resolve/`)
  return resp.data
}

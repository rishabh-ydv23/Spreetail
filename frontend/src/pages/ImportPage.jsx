import React, { useState, useEffect } from 'react'
import { uploadImport, getIssues, commitBatch, getBatch, resolveIssue } from '../api'

// NOTE: set a valid groupId for your environment or extend UI to pick a group.
const DEFAULT_GROUP_ID = 'replace-with-group-id'

export default function ImportPage(){
  const [file, setFile] = useState(null)
  const [batch, setBatch] = useState(null)
  const [issues, setIssues] = useState([])
  const [loading, setLoading] = useState(false)

  async function handleUpload(e){
    e.preventDefault()
    if(!file) return
    setLoading(true)
    try{
      const data = await uploadImport(DEFAULT_GROUP_ID, file)
      setBatch(data)
      if(data.status === 'needs_review'){
        const iss = await getIssues(DEFAULT_GROUP_ID, data.id)
        setIssues(iss)
      }
    }catch(err){
      alert('Upload failed: '+ (err?.response?.data?.detail || err.message))
    }finally{setLoading(false)}
  }

  async function handleResolve(issueId){
    await resolveIssue(DEFAULT_GROUP_ID, batch.id, issueId)
    const iss = await getIssues(DEFAULT_GROUP_ID, batch.id)
    setIssues(iss)
  }

  async function handleCommit(){
    await commitBatch(DEFAULT_GROUP_ID, batch.id, false)
    const updated = await getBatch(DEFAULT_GROUP_ID, batch.id)
    setBatch(updated)
    alert('Batch committed')
  }

  return (
    <div className="import-page">
      <h2>CSV Import</h2>
      <form onSubmit={handleUpload}>
        <input type="file" accept="text/csv" onChange={e=>setFile(e.target.files[0])} />
        <button type="submit" disabled={loading}>Upload</button>
      </form>

      {batch && (
        <div className="batch">
          <h3>Batch: {batch.id} ({batch.status})</h3>
          <pre>{JSON.stringify(batch, null, 2)}</pre>
          {batch.status === 'needs_review' && (
            <div>
              <h4>Issues</h4>
              <ul>
                {issues.map(i=> (
                  <li key={i.id}>
                    <strong>{i.rule_code}</strong>: {i.description}
                    { !i.resolved && <button onClick={()=>handleResolve(i.id)}>Resolve</button> }
                  </li>
                ))}
              </ul>
            </div>
          )}
          {batch.status !== 'completed' && <button onClick={handleCommit}>Commit</button>}
        </div>
      )}
    </div>
  )
}

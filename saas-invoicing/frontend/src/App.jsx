import React, { useState } from 'react'
const API = 'http://localhost:8000'
export default function App() {
  const [token, setToken] = useState('')
  const [out, setOut] = useState('')
  const call = async (path, body) => {
    const r = await fetch(API + path, { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', 'X-Token': token }, body: body ? JSON.stringify(body) : undefined })
    const j = await r.json(); setOut(JSON.stringify(j, null, 2)); return j
  }
  return <div style={{fontFamily:'system-ui',maxWidth:700,margin:'40px auto'}}>
    <h1>SaaS Invoicing</h1>
    <input placeholder="Token" value={token} onChange={e=>setToken(e.target.value)} size={50} />
    <div>
      <button onClick={async()=>{const t=await call('/tenants',{name:'Acme Studio'}); const u=await call('/users',{tenant_id:t.tenant_id,email:'owner@test.com',password:'pw',role:'owner'}); setToken(u.token)}}>Setup demo tenant + owner</button>
      <button onClick={()=>call('/clients',{name:'Client A',email:'c@test.com'})}>Create client</button>
      <button onClick={()=>call('/dashboard')}>Dashboard</button>
    </div>
    <pre>{out}</pre>
    <p>Full flow (clients, invoices, pay) is in the FastAPI backend - see README. This UI proves the React + API wiring end to end.</p>
  </div>
}

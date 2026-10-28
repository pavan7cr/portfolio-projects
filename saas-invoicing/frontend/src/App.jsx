import React, { useState } from 'react'
const API = 'https://saas-invoicing-backend.onrender.com'
export default function App() {
  const [token, setToken] = useState('')
  const [email, setEmail] = useState('owner@test.com')
  const [password, setPassword] = useState('pw123456')
  const [clientId, setClientId] = useState('')
  const [invoiceId, setInvoiceId] = useState('')
  const [out, setOut] = useState('')
  const headers = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, 'X-Token': token }
  const call = async (path, body, method) => {
    const r = await fetch(API + path, { method: method || (body ? 'POST' : 'GET'), headers, body: body ? JSON.stringify(body) : undefined })
    const j = await r.json(); setOut(JSON.stringify(j, null, 2)); return j
  }
  return <div style={{fontFamily:'system-ui',maxWidth:700,margin:'40px auto'}}>
    <h1>SaaS Invoicing</h1>
    <p>Login uses real JWT access tokens. The first user of a tenant is its owner; owners can pay invoices, staff cannot.</p>
    <input placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} size={30} />
    <input placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)} type="password" size={20} />
    <div>
      <button onClick={async()=>{const t=await call('/tenants',{name:'Acme Studio'}); const u=await call('/users',{tenant_id:t.tenant_id,email,password,role:'owner'}); setToken(u.access_token)}}>Setup demo tenant + owner</button>
      <button onClick={async()=>{const u=await call('/login',{email,password}); if (u.access_token) setToken(u.access_token)}}>Login</button>
      <button onClick={async()=>{const c=await call('/clients',{name:'Client A',email:'c@test.com'}); if (c.client_id) setClientId(c.client_id)}}>Create client</button>
      <button onClick={async()=>{const inv=await call('/invoices',{client_id:clientId,items:[{description:'Design work',amount_cents:50000}]}); if (inv.invoice_id) setInvoiceId(inv.invoice_id)}}>Create $500 invoice</button>
      <button onClick={()=>call('/invoices/'+invoiceId+'/pay',{},'POST')}>Pay invoice (owner only)</button>
      <button onClick={()=>call('/dashboard')}>Dashboard</button>
    </div>
    <pre>{out}</pre>
    <p>Backend: FastAPI + JWT + bcrypt + PostgreSQL via DATABASE_URL (SQLite locally). Stripe is not integrated; pay only marks an invoice paid locally.</p>
  </div>
}

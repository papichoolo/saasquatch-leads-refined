import { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import axios from 'axios'
import EmailModal from '../components/EmailModal'
import '../styles/ResultsPage.css'

function ResultsPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { keyword, location: searchLocation } = location.state || {}
  
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedLeads, setSelectedLeads] = useState(new Set())
  const [showEmailModal, setShowEmailModal] = useState(false)
  const [currentLead, setCurrentLead] = useState(null)
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })
  const [minRating, setMinRating] = useState(0)
  const [hasEmailFilter, setHasEmailFilter] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0 })
  const [isStreaming, setIsStreaming] = useState(false)
  const [enrichingLeads, setEnrichingLeads] = useState(new Set())

  useEffect(() => {
    if (!keyword || !searchLocation) {
      navigate('/')
      return
    }
    fetchLeads()
  }, [keyword, searchLocation])

  const fetchLeads = async () => {
    setLoading(true)
    setIsStreaming(true)
    setError('')
    setLeads([])
    setProgress({ current: 0, total: 0 })
    
    try {
      const response = await fetch('/v1/enrich.ndjson', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          keyword,
          location: searchLocation,
          max_results: 20,
          skip_enrichment: false,
          max_pages_per_site: 2
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      
      while (true) {
        const { done, value } = await reader.read()
        
        if (done) break
        
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        
        // Keep the last incomplete line in buffer
        buffer = lines.pop() || ''
        
        for (const line of lines) {
          if (!line.trim()) continue
          
          try {
            const obj = JSON.parse(line)
            
            if (obj.type === 'meta') {
              setProgress(prev => ({ ...prev, total: obj.total }))
            } else if (obj.type === 'item') {
              setLeads(prev => [...prev, obj])
              setProgress(prev => ({ ...prev, current: obj.idx }))
            } else if (obj.type === 'complete') {
              setIsStreaming(false)
            }
          } catch (e) {
            console.error('Failed to parse line:', line, e)
          }
        }
      }
      
      setLoading(false)
    } catch (err) {
      setError('Failed to fetch leads. Please try again.')
      console.error(err)
      setLoading(false)
      setIsStreaming(false)
    }
  }

  const toggleSelect = (idx) => {
    const newSelected = new Set(selectedLeads)
    if (newSelected.has(idx)) {
      newSelected.delete(idx)
    } else {
      newSelected.add(idx)
    }
    setSelectedLeads(newSelected)
  }

  const toggleSelectAll = () => {
    if (selectedLeads.size === filteredLeads.length) {
      setSelectedLeads(new Set())
    } else {
      setSelectedLeads(new Set(filteredLeads.map((_, idx) => idx)))
    }
  }

  const handleSort = (key) => {
    let direction = 'asc'
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc'
    }
    setSortConfig({ key, direction })
  }

  const handleGenerateEmail = (lead) => {
    setCurrentLead(lead)
    setShowEmailModal(true)
  }

  const handleFindEmail = async (lead, leadIndex) => {
    setEnrichingLeads(prev => new Set([...prev, leadIndex]))
    
    try {
      const response = await axios.post('/v1/tavily-enrich', {
        name: lead.name,
        website: lead.website,
        location: lead.address,
        existing_emails: lead.emails || [],
        existing_linkedin: lead.linkedin,
        max_queries: 3,
        fetch_pages: false
      })
      
      // Update the lead with enriched data
      setLeads(prevLeads => {
        const newLeads = [...prevLeads]
        const targetLead = newLeads.find(l => l.idx === lead.idx)
        if (targetLead) {
          targetLead.emails = response.data.emails || []
          targetLead.linkedin = response.data.linkedin || targetLead.linkedin
          targetLead.tavily_enriched = true
          targetLead.tavily_cost = response.data.cost_estimate_usd
        }
        return newLeads
      })
    } catch (err) {
      console.error('Tavily enrichment failed:', err)
      alert('Failed to find email. Please try again.')
    } finally {
      setEnrichingLeads(prev => {
        const newSet = new Set(prev)
        newSet.delete(leadIndex)
        return newSet
      })
    }
  }

  const exportCSV = () => {
    const headers = ['Name', 'Address', 'Phone', 'Website', 'Emails', 'LinkedIn']
    const rows = filteredLeads.map(lead => [
      lead.name || '',
      lead.address || '',
      lead.phone || '',
      lead.website || '',
      (lead.emails || []).join('; '),
      lead.linkedin || ''
    ])
    
    const csv = [headers, ...rows].map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `leads-${keyword.replace(/\s+/g, '-')}.csv`
    a.click()
  }

  // Filter logic
  const filteredLeads = leads.filter(lead => {
    if (minRating > 0 && (!lead.rating || lead.rating < minRating)) {
      return false
    }
    if (hasEmailFilter && (!lead.emails || lead.emails.length === 0)) {
      return false
    }
    return true
  })

  // Sort logic
  const sortedLeads = [...filteredLeads].sort((a, b) => {
    if (!sortConfig.key) return 0
    
    const aVal = a[sortConfig.key]
    const bVal = b[sortConfig.key]
    
    if (aVal === bVal) return 0
    if (aVal === null || aVal === undefined) return 1
    if (bVal === null || bVal === undefined) return -1
    
    const comparison = aVal > bVal ? 1 : -1
    return sortConfig.direction === 'asc' ? comparison : -comparison
  })

  if (!keyword || !searchLocation) {
    return null
  }

  return (
    <div className="results-page">
      <header className="results-header">
        <div className="header-content">
          <button className="back-button" onClick={() => navigate('/')}>← Back to Search</button>
          <h1 className="results-title">Results for "{keyword}" in {searchLocation}</h1>
          <p className="results-summary">
            {loading ? 'Loading...' : `${filteredLeads.length} leads found`}
          </p>
        </div>
      </header>

      <div className="results-container">
        <aside className="filters-sidebar">
          <h3>Filters</h3>
          
          <div className="filter-group">
            <label htmlFor="min-rating">Minimum Rating</label>
            <select 
              id="min-rating"
              value={minRating} 
              onChange={(e) => setMinRating(Number(e.target.value))}
            >
              <option value="0">Any</option>
              <option value="3">3+ ⭐</option>
              <option value="4">4+ ⭐</option>
              <option value="4.5">4.5+ ⭐</option>
            </select>
          </div>

          <div className="filter-group">
            <label>
              <input 
                type="checkbox" 
                checked={hasEmailFilter}
                onChange={(e) => setHasEmailFilter(e.target.checked)}
              />
              <span>Has Email Only</span>
            </label>
          </div>

          <button className="export-button" onClick={exportCSV} disabled={filteredLeads.length === 0}>
            Export CSV
          </button>
        </aside>

        <main className="results-main">
          {error ? (
            <div className="error">{error}</div>
          ) : (
            <>
              {isStreaming && progress.total > 0 && (
                <div className="progress-container">
                  <div className="progress-header">
                    <span className="progress-text">
                      Enriching leads... {progress.current} of {progress.total}
                    </span>
                    <span className="progress-percent">
                      {Math.round((progress.current / progress.total) * 100)}%
                    </span>
                  </div>
                  <div className="progress-bar">
                    <div 
                      className="progress-fill" 
                      style={{ width: `${(progress.current / progress.total) * 100}%` }}
                    />
                  </div>
                </div>
              )}
              
              <div className="table-container">
              <table className="results-table">
                <thead>
                  <tr>
                    <th>
                      <input 
                        type="checkbox" 
                        checked={selectedLeads.size === filteredLeads.length && filteredLeads.length > 0}
                        onChange={toggleSelectAll}
                      />
                    </th>
                    <th onClick={() => handleSort('name')} className="sortable">
                      Business Name {sortConfig.key === 'name' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                    </th>
                    <th onClick={() => handleSort('address')} className="sortable">
                      Address {sortConfig.key === 'address' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                    </th>
                    <th>Website</th>
                    <th>Phone</th>
                    <th>Emails</th>
                    <th>LinkedIn</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLeads.map((lead, idx) => (
                    <tr key={idx} className={selectedLeads.has(idx) ? 'selected' : ''}>
                      <td>
                        <input 
                          type="checkbox" 
                          checked={selectedLeads.has(idx)}
                          onChange={() => toggleSelect(idx)}
                        />
                      </td>
                      <td className="business-name">{lead.name || 'N/A'}</td>
                      <td className="address">{lead.address || 'N/A'}</td>
                      <td>
                        {lead.website ? (
                          <a href={lead.website} target="_blank" rel="noopener noreferrer" className="link-icon">
                            🔗
                          </a>
                        ) : 'N/A'}
                      </td>
                      <td>{lead.phone ? `📞 ${lead.phone}` : 'N/A'}</td>
                      <td>
                        {lead.emails && lead.emails.length > 0 ? (
                          <div className="emails-cell">
                            {lead.emails.slice(0, 2).map((email, i) => (
                              <div key={i} className="email-item">{email}</div>
                            ))}
                            {lead.emails.length > 2 && (
                              <span className="more-emails">+{lead.emails.length - 2} more</span>
                            )}
                            {lead.tavily_enriched && (
                              <span className="enriched-badge" title={`Cost: $${lead.tavily_cost}`}>
                                AI ✨
                              </span>
                            )}
                          </div>
                        ) : (
                          <button 
                            className="find-email-btn"
                            onClick={() => handleFindEmail(lead, idx)}
                            disabled={enrichingLeads.has(idx) || !lead.website}
                            title="Use Tavily AI to find emails"
                          >
                            {enrichingLeads.has(idx) ? '🔄 Finding...' : '🔍 Find Email'}
                          </button>
                        )}
                      </td>
                      <td>
                        {lead.linkedin ? (
                          <a href={lead.linkedin} target="_blank" rel="noopener noreferrer" className="linkedin-link">
                            View
                          </a>
                        ) : 'N/A'}
                      </td>
                      <td>
                        <button 
                          className="generate-email-btn"
                          onClick={() => handleGenerateEmail(lead)}
                          disabled={!lead.website || (!lead.emails || lead.emails.length === 0)}
                        >
                          Generate Email
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              
              {sortedLeads.length === 0 && !loading && !isStreaming && (
                <div className="no-results">No leads match your filters.</div>
              )}
            </div>
            </>
          )}
        </main>
      </div>

      {showEmailModal && currentLead && (
        <EmailModal 
          lead={currentLead}
          onClose={() => setShowEmailModal(false)}
        />
      )}
    </div>
  )
}

export default ResultsPage

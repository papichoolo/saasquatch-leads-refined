import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import '../styles/SearchPage.css'

function SearchPage() {
  const [keyword, setKeyword] = useState('')
  const [location, setLocation] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleSearch = (e) => {
    e.preventDefault()
    
    if (!keyword.trim()) {
      setError('Please enter what you are looking for')
      return
    }
    
    if (!location.trim()) {
      setError('Please enter a location')
      return
    }

    setError('')
    navigate('/results', { state: { keyword: keyword.trim(), location: location.trim() } })
  }

  return (
    <div className="search-page">
      <div className="search-container">
        <header className="search-header">
          <h1 className="search-title">SaaSquatchLeads-Refined</h1>
        </header>

        <div className="search-card">
          <form onSubmit={handleSearch}>
            <div className="form-group">
              <label htmlFor="keyword">What are you looking for?</label>
              <input
                id="keyword"
                type="text"
                className="search-input"
                placeholder="e.g. digital marketing agencies, cafes, accounting firms"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="location">Where are you looking?</label>
              <input
                id="location"
                type="text"
                className="search-input"
                placeholder="e.g. Bangalore, India"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </div>

            {error && <div className="error-message">{error}</div>}

            <button type="submit" className="search-button">
              Find Leads
            </button>

            <p className="powered-by">Powered by Google Places API</p>
          </form>
        </div>

        <footer className="search-footer">
          <p>Your data is never stored.</p>
        </footer>
      </div>
    </div>
  )
}

export default SearchPage

import { useState, useEffect } from 'react'
import axios from 'axios'
import '../styles/EmailModal.css'

function EmailModal({ lead, onClose }) {
  const [emailData, setEmailData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [recipientEmail, setRecipientEmail] = useState('')
  const [editedBody, setEditedBody] = useState('')
  const [showSmtpConfig, setShowSmtpConfig] = useState(false)
  
  // Company context state (loaded from localStorage)
  const [companyName, setCompanyName] = useState(localStorage.getItem('company_name') || '')
  const [companyWebsite, setCompanyWebsite] = useState(localStorage.getItem('company_website') || '')
  const [companySector, setCompanySector] = useState(localStorage.getItem('company_sector') || '')
  const [outreachReason, setOutreachReason] = useState(localStorage.getItem('outreach_reason') || '')
  
  // SMTP Configuration state (loaded from localStorage)
  const [smtpUser, setSmtpUser] = useState(localStorage.getItem('smtp_user') || '')
  const [smtpPass, setSmtpPass] = useState(localStorage.getItem('smtp_pass') || '')

  // Step state: 'input' or 'preview'
  const [step, setStep] = useState('input')

  useEffect(() => {
    // Set default email
    if (lead.emails && lead.emails.length > 0) {
      setRecipientEmail(lead.emails[0])
    }
  }, [])

  const generateEmail = async () => {
    // Validate required fields
    if (!companyName.trim()) {
      setError('Please enter your company name')
      return
    }
    if (!companyWebsite.trim()) {
      setError('Please enter your company website')
      return
    }
    if (!companySector.trim()) {
      setError('Please enter your company sector')
      return
    }
    if (!outreachReason.trim()) {
      setError('Please explain why you\'re reaching out')
      return
    }

    setLoading(true)
    setError('')
    
    // Save to localStorage for future use
    localStorage.setItem('company_name', companyName)
    localStorage.setItem('company_website', companyWebsite)
    localStorage.setItem('company_sector', companySector)
    localStorage.setItem('outreach_reason', outreachReason)
    
    try {
      const response = await axios.post('/v1/generate-email', {
        name: lead.name,
        website: lead.website,
        rec_email: lead.emails?.[0] || 'contact@example.com',
        company_sector: companySector,
        outreach_reason: outreachReason,
        sender_website: companyWebsite
      })
      
      setEmailData(response.data)
      setEditedBody(response.data.body)
      setStep('preview')
    } catch (err) {
      setError('Failed to generate email. Please try again.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = () => {
    setStep('input')
    setError('')
  }

  const handleCopy = () => {
    const fullEmail = `Subject: ${emailData.subject}\n\nTo: ${recipientEmail}\n\n${editedBody}`
    navigator.clipboard.writeText(fullEmail)
    alert('Email copied to clipboard!')
  }

  const handleSend = async () => {
    if (!recipientEmail) {
      alert('Please select a recipient email address')
      return
    }

    if (!smtpUser || !smtpPass) {
      alert('Please configure your SMTP email and app password in the settings')
      setShowSmtpConfig(true)
      return
    }

    try {
      setLoading(true)
      
      // Save SMTP credentials to localStorage
      localStorage.setItem('smtp_user', smtpUser)
      localStorage.setItem('smtp_pass', smtpPass)
      
      await axios.post('/v1/send', {
        to: [recipientEmail],
        subject: emailData.subject,
        body: editedBody,
        is_html: false,
        smtp_user: smtpUser,
        smtp_pass: smtpPass
      })
      alert(`Email sent successfully to ${recipientEmail}!`)
      onClose()
    } catch (error) {
      console.error('Error sending email:', error)
      const errorMsg = error.response?.data?.detail || 'Failed to send email. Please check your SMTP configuration.'
      alert(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{step === 'input' ? 'Your Company Details' : `Generate Email for ${lead.name}`}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {step === 'input' ? (
            // Step 1: Collect company information
            <>
              <div className="input-section">
                <p className="section-description">
                  Provide your company details to generate a personalized email
                </p>

                {error && <div className="modal-error">{error}</div>}

                <div className="form-field">
                  <label htmlFor="company-name">Your Company Name *</label>
                  <input 
                    id="company-name"
                    type="text" 
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="e.g., Acme Inc"
                    className="input-field"
                  />
                </div>

                <div className="form-field">
                  <label htmlFor="company-website">Your Company Website *</label>
                  <input 
                    id="company-website"
                    type="url" 
                    value={companyWebsite}
                    onChange={(e) => setCompanyWebsite(e.target.value)}
                    placeholder="e.g., https://acme.com"
                    className="input-field"
                  />
                </div>

                <div className="form-field">
                  <label htmlFor="company-sector">Your Company Sector *</label>
                  <input 
                    id="company-sector"
                    type="text" 
                    value={companySector}
                    onChange={(e) => setCompanySector(e.target.value)}
                    placeholder="e.g., B2B SaaS, Lead Generation, Marketing Automation"
                    className="input-field"
                  />
                  <small className="field-help">What industry does your company operate in?</small>
                </div>

                <div className="form-field">
                  <label htmlFor="outreach-reason">Why are you reaching out? *</label>
                  <textarea 
                    id="outreach-reason"
                    rows="4"
                    value={outreachReason}
                    onChange={(e) => setOutreachReason(e.target.value)}
                    placeholder="e.g., We help companies like yours find qualified B2B leads through AI-powered enrichment"
                    className="input-field"
                  />
                  <small className="field-help">Explain the value you provide to this lead</small>
                </div>

                <div className="modal-actions">
                  <button className="btn-secondary" onClick={onClose}>
                    Cancel
                  </button>
                  <button 
                    className="btn-primary" 
                    onClick={generateEmail}
                    disabled={loading}
                  >
                    {loading ? '⏳ Generating...' : '✨ Generate Email'}
                  </button>
                </div>
              </div>
            </>
          ) : (
            // Step 2: Preview and edit email
            <>
              {loading ? (
                <div className="modal-loading">Generating personalized email...</div>
              ) : error ? (
                <div className="modal-error">{error}</div>
              ) : (
                <>
                  <div className="form-row">
                    <div className="form-field">
                      <label htmlFor="recipient-name">Recipient Name</label>
                      <input 
                        id="recipient-name"
                        type="text" 
                        value={lead.name}
                        readOnly
                        className="readonly-input"
                      />
                    </div>

                    <div className="form-field">
                      <label htmlFor="company-name">Company Website</label>
                      <input 
                        id="company-name"
                        type="text" 
                        value={lead.website}
                        readOnly
                        className="readonly-input"
                      />
                    </div>
                  </div>

                  <div className="form-field">
                    <label htmlFor="recipient-email">Email Address</label>
                    <select 
                      id="recipient-email"
                      value={recipientEmail}
                      onChange={(e) => setRecipientEmail(e.target.value)}
                    >
                      {lead.emails && lead.emails.map((email, idx) => (
                        <option key={idx} value={email}>{email}</option>
                      ))}
                    </select>
                  </div>

                  <div className="form-field">
                    <label htmlFor="email-subject">Subject</label>
                    <input 
                      id="email-subject"
                      type="text" 
                      value={emailData?.subject || ''}
                      readOnly
                      className="readonly-input"
                    />
                  </div>

                  <div className="form-field">
                    <label htmlFor="email-body">Email Body</label>
                    <textarea 
                      id="email-body"
                      rows="12"
                      value={editedBody}
                      onChange={(e) => setEditedBody(e.target.value)}
                      className="email-textarea"
                    />
                  </div>

                  {/* SMTP Configuration Section */}
                  <div className="smtp-config-section">
                    <button 
                      className="btn-config"
                      onClick={() => setShowSmtpConfig(!showSmtpConfig)}
                      type="button"
                    >
                      ⚙️ {showSmtpConfig ? 'Hide' : 'Configure'} SMTP Settings
                    </button>
                    
                    {showSmtpConfig && (
                      <div className="smtp-config-form">
                        <div className="form-field">
                          <label htmlFor="smtp-user">Your Email (SMTP User)</label>
                          <input 
                            id="smtp-user"
                            type="email"
                            placeholder="your-email@gmail.com"
                            value={smtpUser}
                            onChange={(e) => setSmtpUser(e.target.value)}
                            className="smtp-input"
                          />
                          <small className="field-help">The email address you'll send from</small>
                        </div>

                        <div className="form-field">
                          <label htmlFor="smtp-pass">App Password</label>
                          <input 
                            id="smtp-pass"
                            type="password"
                            placeholder="xxxx xxxx xxxx xxxx"
                            value={smtpPass}
                            onChange={(e) => setSmtpPass(e.target.value)}
                            className="smtp-input"
                          />
                          <small className="field-help">
                            For Gmail: <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">Generate app password</a>
                          </small>
                        </div>

                        <div className="smtp-status">
                          {smtpUser && smtpPass ? '✅ SMTP configured' : '⚠️ SMTP not configured'}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="modal-actions">
                    <button className="btn-secondary" onClick={handleRegenerate} disabled={loading}>
                      ← Back
                    </button>
                    <button className="btn-secondary" onClick={handleCopy} disabled={loading}>
                      📋 Copy Email
                    </button>
                    <button className="btn-primary" onClick={handleSend} disabled={loading || !recipientEmail}>
                      {loading ? '⏳ Sending...' : '📧 Send'}
                    </button>
                  </div>

                  <div className="modal-status">
                    {loading ? '⏳ Processing...' : '✅ Email ready to send via SMTP'}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default EmailModal

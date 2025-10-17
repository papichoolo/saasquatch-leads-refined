import { useState, useEffect } from 'react'
import axios from 'axios'
import '../styles/EmailModal.css'

function EmailModal({ lead, onClose }) {
  const [emailData, setEmailData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [recipientEmail, setRecipientEmail] = useState('')
  const [editedBody, setEditedBody] = useState('')
  const [hasGenerated, setHasGenerated] = useState(false)
  const [showSmtpConfig, setShowSmtpConfig] = useState(false)
  
  // SMTP Configuration state (loaded from localStorage)
  const [smtpUser, setSmtpUser] = useState(localStorage.getItem('smtp_user') || '')
  const [smtpPass, setSmtpPass] = useState(localStorage.getItem('smtp_pass') || '')

  useEffect(() => {
    // Set default email
    if (lead.emails && lead.emails.length > 0) {
      setRecipientEmail(lead.emails[0])
    }
    // Only generate once
    if (!hasGenerated) {
      setHasGenerated(true)
      generateEmail()
    }
  }, [])

  const generateEmail = async () => {
    setLoading(true)
    setError('')
    
    try {
      const response = await axios.post('/v1/generate-email', {
        name: lead.name,
        website: lead.website,
        rec_email: lead.emails?.[0] || 'contact@example.com'
      })
      
      setEmailData(response.data)
      setEditedBody(response.data.body)
    } catch (err) {
      setError('Failed to generate email. Please try again.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = () => {
    setHasGenerated(true) // Mark as generated to prevent duplicate on re-render
    generateEmail()
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
          <h2>Generate Email for {lead.name}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
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
                  🔄 Regenerate
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
        </div>
      </div>
    </div>
  )
}

export default EmailModal

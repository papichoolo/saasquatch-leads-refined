# SaaSquatch Leads Refined

A full-stack lead enrichment and outreach tool using Google Places, Tavily AI, and personalized email generation.

## Features
- Enriches business leads with emails and LinkedIn using Google Places and Tavily AI
- Batch and single-lead enrichment
- Personalized cold email generation (Google GenAI)
- Frontend UI for searching, enrichment, and email sending
- User-configurable SMTP (Gmail) for sending emails
- Optional MongoDB or CSV persistence

---

## Quick Start

### 1. Clone the Repository
```sh
git clone https://github.com/yourusername/saasquatch-leads-refined.git
cd saasquatch-leads-refined
```

### 2. Python Backend Setup
- Requires Python 3.9+
- Install dependencies:
```sh
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```
- Create `.env` and fill in:
  - `GOOGLE_MAPS` (Google Places API key)
  - `TAVILY_API_KEY` (Tavily API key)
  - `GMAIL_PASSWORD` (for default SMTP, or leave blank for user config)
  - `SMTP_USER` (for default SMTP, or leave blank for user config)
- Start the backend:
```sh
python app.py
```

### 3. Frontend Setup
- Requires Node.js 18+
- Install dependencies:
```sh
cd frontend
npm install
```
- Start the frontend dev server:
```sh
npm run dev
```
- The app will open at [http://localhost:3000](http://localhost:3000)

### 4. Using the App
- Search for leads and enrich them
- Click a lead to open the email modal
- Click "⚙️ Configure SMTP Settings" and enter your Gmail and app password ([generate here](https://myaccount.google.com/apppasswords))
- Send personalized emails directly from the UI

---

## API Endpoints
- `POST /v1/enrich.ndjson` — Stream enriched leads (Google Places)
- `POST /v1/tavily-enrich` — Enrich a single lead with Tavily API
- `POST /v1/generate-email` — Generate a personalized cold email
- `POST /v1/send` — Send email (requires SMTP credentials)

---

## Environment Variables
See `.env.example` for all required variables. Never commit your real `.env` file.

---

## MongoDB (Optional)
- Set `MONGO_URI` in `.env` to enable MongoDB persistence for leads.
- If not set, CSV fallback is used.

---

## CSV Fallback
- By default, leads are persisted to `leads_from_api.csv`.

---

## Security Notes
- Never commit `.env` or credentials to git.
- SMTP credentials are stored in browser localStorage for user convenience.
- Use Gmail app passwords, not your main password.

---

## License
MIT

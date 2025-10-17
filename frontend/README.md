# Local Lead Finder - Frontend

Modern React + Vite frontend for the Local Lead Finder application.

## Quick Start

```powershell
# Install dependencies
cd frontend
npm install

# Start development server (with API proxy)
npm run dev
```

The app will run on `http://localhost:3000` and proxy API requests to `http://localhost:8000`.

## Features

- ✅ **Search Page** - Find leads by keyword and location
- ✅ **Results Dashboard** - View enriched leads in a sortable table
- ✅ **Email Generation** - AI-powered personalized cold emails
- ✅ **Filters** - Min rating, has email only
- ✅ **Export CSV** - Download leads for offline use
- ✅ **Responsive Design** - Works on desktop and mobile

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   └── EmailModal.jsx
│   ├── pages/
│   │   ├── SearchPage.jsx
│   │   └── ResultsPage.jsx
│   ├── styles/
│   │   ├── SearchPage.css
│   │   ├── ResultsPage.css
│   │   └── EmailModal.css
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── index.html
├── vite.config.js
└── package.json
```

## API Integration

The frontend connects to these FastAPI endpoints:

- `POST /v1/enrich.ndjson` - Fetch and enrich leads
- `POST /v1/generate-email` - Generate personalized email

## Design System

- **Primary Color**: `#2563EB` (blue-600)
- **Background**: `#F9FAFB`
- **Accent**: `#FACC15` (yellow-400)
- **Text**: `#111827`
- **Font**: Inter

## Build for Production

```powershell
npm run build
```

Outputs to `dist/` folder.

## Development Notes

- Hot module replacement enabled
- API proxy configured in `vite.config.js`
- Uses axios for HTTP requests
- React Router for navigation

# Netlify Deploy Guide

Netlify can host only the static frontend in this project. The LinkedIn automation bot still needs the Python Flask backend because it uses Selenium, Chrome, local CSV files, and a long-running process.

## Fix Page Not Found

This project now includes:

- `index.html` for Netlify to serve.
- `_redirects` so routes like `/configuration/general` open the frontend instead of 404.
- `netlify.toml` with the publish directory set to the project root.

## Deploy Steps

1. Push this project to GitHub or upload the full project folder to Netlify.
2. In Netlify, use these build settings:
   - Build command: leave empty
   - Publish directory: `.`
3. Deploy the site.
4. Run the Python backend separately:

```powershell
python .\app.py
```

5. Open the Netlify site and enter your backend API URL.

Local backend default:

```text
http://127.0.0.1:8080
```

## Important

If you want users outside your computer to control the bot, host the Python backend on a server that supports Chrome/Selenium and expose it with HTTPS. Netlify alone cannot run the bot backend.

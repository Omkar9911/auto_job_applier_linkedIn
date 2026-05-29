# Vercel Deploy Guide

Vercel can host the static frontend in this project, but it cannot run the full LinkedIn automation bot as a long-running Selenium/Chrome process.

The bot backend must run separately because it needs:

- Python Flask server
- Selenium
- Google Chrome / ChromeDriver
- local CSV files
- a long-running process for Start Bot / Stop Bot

## What Vercel Will Host

This repository includes:

- `index.html` - static Vercel frontend shell
- `vercel.json` - routes all Vercel paths to `index.html`

## Vercel Deploy Steps

1. Push this repository to GitHub.
2. Import the GitHub repository into Vercel.
3. Use these settings:
   - Framework Preset: Other
   - Build Command: leave empty
   - Output Directory: leave empty or `.`
4. Deploy.
5. Run the Python backend separately:

```powershell
python .\app.py
```

6. Open the Vercel URL and set Backend API URL.

Local backend default:

```text
http://127.0.0.1:8080
```

## For Public Users

If other users need to access the bot from the internet, deploy the Python backend to a long-running server/VPS that supports Chrome/Selenium, then enter that public HTTPS backend URL in the Vercel frontend.

Recommended backend hosts:

- VPS such as DigitalOcean, AWS EC2, Azure VM, or Google Compute Engine
- Docker-capable server with Chrome installed
- Any Python hosting platform that supports long-running processes and browser automation

Vercel should be used for the frontend only.

# BioLoQ on Render

## Important
This app uses a Python backend and SQLite file. The frontend must call relative API paths (`/api`), which is already fixed in this folder.

## Upload to GitHub
Upload all files in this folder to a GitHub repository.

## Create Render Web Service
- New + -> Web Service
- Connect GitHub repo
- Environment: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `python server.py`

## Optional settings
- Add environment variable `PYTHON_VERSION=3.11.9` if needed

## After deploy
Open your Render URL, for example `https://bioloq.onrender.com`

## Note about database persistence
`question_bank.db` is a local SQLite file. On free/standard ephemeral instances, changes may be lost on redeploy/restart. For durable storage, move later to a server database or attach persistent disk on a plan that supports it.

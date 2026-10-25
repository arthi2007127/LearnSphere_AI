# LearnSphere AI

LearnSphere AI is a Flask learning and placement-preparation platform. It brings aptitude practice, coding challenges, interview preparation, English coaching, AI study assistance, and a weekly placement plan into one learner workspace.

## Features

- Aptitude practice and topic guides
- Code Lab with AI-generated coding challenges
- Interview Hub with 100 practice levels
- English Coach with writing and pronunciation feedback
- AI Coach and Study Assistant
- Placement Plan with saved task completion
- Account registration, login, and password reset flows
- Learner progress stored in SQLAlchemy models
- Daily learning streaks and a live homepage progress card based on completed activities

## Run locally

1. Create and activate a Python 3.12 virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set the values you need.
4. Start the server with `flask --app app run`.

The local default database is SQLite at `instance/learnsphere.db`. AI features need a valid `GEMINI_API_KEY`. Password reset email needs SMTP configuration.

## Deploy on Render

This repository includes `render.yaml` for a Render Blueprint. Connect the GitHub repository in Render and create a Blueprint from it. Set `GEMINI_API_KEY` in the Render service environment after the Blueprint is created. Add SMTP variables only when using a mail provider that supports Render's outbound network rules.

The Blueprint uses a free web service and free PostgreSQL database for a demo. Render's free web services sleep after inactivity; free PostgreSQL expires 30 days after creation and should not be used for long-lived learner data. Choose paid resources before using the platform for real learner accounts or persistent progress. See [Render's free service limits](https://render.com/docs/free).

## Configuration

See `.env.example` for supported environment variable names. Never commit `.env`, API keys, mail credentials, or database files.

## Project map

- `app.py` — routes, authentication, learning flows, and persistence
- `models.py` — user and learner progress models
- `config.py` — environment and database configuration
- `services/` — Gemini-backed learning services
- `templates/` — Flask/Jinja pages
- `static/` — stylesheets and frontend assets
- `LearnSphere_AI_Project_Overview.docx` and `.pdf` — project overview

The homepage progress card counts completed aptitude, coding, interview, and communication practice for the current day. It updates when a result or completed practice is saved; simply opening a page does not increase progress. A learning streak advances once per calendar day with recorded practice.


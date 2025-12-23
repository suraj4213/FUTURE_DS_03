# College Event Feedback Analysis

A Flask web app for collecting, analyzing, and visualizing event feedback using Supabase as a backend and pandas/Plotly for analytics.

## Features
- Upload feedback via form or CSV
- Store feedback in Supabase and locally
- Dashboard with sentiment, satisfaction, and suggestions
- Export analytics as PDF

## Deployment
- Deployable on Vercel (see `vercel.json`)
- Python 3.8+

## Setup
1. Clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Install dependencies: `pip install openpyxl`
4. Set up `.env` with your Supabase credentials
5. Run locally: `python app.py`

## Environment Variables
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SECRET_KEY`

## License
See [LICENSE](LICENSE).

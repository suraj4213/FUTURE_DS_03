# Vercel Deployment Guide

## Prerequisites

1. **Vercel Account**: Sign up at https://vercel.com
2. **GitHub Repository**: Push your code to GitHub

## Deployment Steps

### 1. Connect to Vercel
- Go to https://vercel.com/dashboard
- Click "Add New Project"
- Import your GitHub repository

### 2. Configure Environment Variables
In Vercel Dashboard → Settings → Environment Variables, add:
- `SUPABASE_URL` (optional, if using Supabase)
- `SUPABASE_KEY` (optional, if using Supabase)
- `SECRET_KEY` (optional, default: 'changeme')

### 3. Deploy
- Vercel will automatically detect `vercel.json` and deploy
- The deployment will use Python 3.x runtime

## Important Notes

### File Storage
- **Excel files**: Stored in `/tmp/feedback_data.xlsx` (ephemeral storage)
- **Note**: Files in `/tmp` are deleted between invocations on Vercel
- **Recommendation**: Use Supabase for persistent storage instead

### Static Files
- Static files in `/static` folder are served automatically
- Templates in `/templates` are included in the deployment

### Serverless Limitations
- Cold starts: First request may be slower
- Memory limits: 3000 MB max on Vercel Pro
- Execution timeout: 10s (Hobby) or 60s (Pro)
- Read-only filesystem except `/tmp` directory

## Troubleshooting

### Common Issues

1. **Module not found errors**
   - Ensure all dependencies are in `requirements.txt`
   - Check Vercel build logs for missing packages

2. **Excel file not saving**
   - Files must be saved to `/tmp/` directory
   - Data will be lost between invocations
   - Use Supabase for persistent storage

3. **Static files not loading**
   - Check that files are in `/static` directory
   - Verify routes in `vercel.json`

4. **Environment variables not working**
   - Set them in Vercel Dashboard → Settings → Environment Variables
   - Redeploy after adding variables

## Configuration Files

- `vercel.json`: Vercel deployment configuration
- `requirements.txt`: Python dependencies
- `.vercelignore`: Files to exclude from deployment


import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for
from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import plotly.graph_objs as go
import plotly
import json
from datetime import datetime


from werkzeug.utils import secure_filename
# Supabase integration
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SECRET_KEY = os.getenv('SECRET_KEY', 'changeme')

# Initialize Flask app with explicit static and template folders for Vercel
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = SECRET_KEY

# Supabase client
if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("Warning: Supabase credentials not found. Some features may not work.")


# Data storage (Excel file for feedback when Supabase is not available)
# Use /tmp directory for serverless environments like Vercel
if os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
    # Serverless environment - use /tmp directory
    EXCEL_FILE = '/tmp/feedback_data.xlsx'
else:
    # Local environment - use current directory
    EXCEL_FILE = 'feedback_data.xlsx'

# Theme keywords for advanced categorization
THEME_KEYWORDS = {
    'speaker quality': ['speaker', 'presentation', 'presenter', 'knowledge', 'engagement', 'delivery', 'clarity'],
    'organization': ['organization', 'timing', 'schedule', 'coordination', 'communication', 'managed', 'arrangement'],
    'venue': ['venue', 'location', 'facilities', 'seating', 'audio', 'visual', 'projector', 'mic', 'sound', 'hall'],
    'content': ['content', 'relevance', 'depth', 'usefulness', 'material', 'topic', 'agenda'],
    'networking': ['networking', 'interaction', 'peer', 'engagement', 'connect', 'discussion', 'group']
}

import re
from collections import Counter, defaultdict

# Helper functions for Excel storage (when Supabase is not available)
def save_feedback_to_excel(feedback_data):
    """Save feedback data to Excel file"""
    try:
        # Check if openpyxl is available
        try:
            import openpyxl
        except ImportError:
            raise Exception("openpyxl module is not installed. Please install it with: pip install openpyxl")
        
        # Define all required columns
        columns = [
            'event_name', 'event_date', 'event_type', 'department', 'year_of_study',
            'satisfaction_rating', 'liked', 'suggestions', 'comments', 'categories',
            'sentiment', 'satisfaction_level', 'objectivity', 'category'
        ]
        
        # Create DataFrame from new feedback data
        print(f"Creating DataFrame from feedback data...")
        df_new = pd.DataFrame([feedback_data])
        
        # Ensure all columns exist in the new DataFrame
        for col in columns:
            if col not in df_new.columns:
                df_new[col] = ''
        
        # Reorder columns to match expected order
        df_new = df_new[columns]
        print(f"New DataFrame created with {len(df_new)} row(s) and {len(df_new.columns)} columns")
        
        # Get absolute path for Excel file
        excel_path = os.path.abspath(EXCEL_FILE)
        # Ensure directory exists (especially important for /tmp in serverless)
        excel_dir = os.path.dirname(excel_path)
        if excel_dir and not os.path.exists(excel_dir):
            try:
                os.makedirs(excel_dir, exist_ok=True)
            except Exception as e:
                print(f"Warning: Could not create directory {excel_dir}: {e}")
        print(f"Excel file path: {excel_path}")
        
        if os.path.exists(excel_path):
            try:
                print(f"Reading existing Excel file...")
                # Read existing Excel file
                df_existing = pd.read_excel(excel_path, engine='openpyxl')
                print(f"Existing file has {len(df_existing)} records")
                
                # Ensure all columns exist in existing DataFrame
                for col in columns:
                    if col not in df_existing.columns:
                        df_existing[col] = ''
                
                # Reorder existing DataFrame columns
                df_existing = df_existing[columns]
                
                # Combine existing and new data
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                print(f"Combined DataFrame has {len(df_combined)} records")
            except Exception as read_error:
                print(f"Warning: Error reading existing Excel file: {read_error}. Creating new file.")
                import traceback
                traceback.print_exc()
                df_combined = df_new
        else:
            print(f"Excel file does not exist. Creating new file...")
            df_combined = df_new
        
        # Save to Excel file
        print(f"Saving to Excel file: {excel_path}")
        df_combined.to_excel(excel_path, index=False, engine='openpyxl')
        print(f"Excel file saved successfully")
        
        # Verify file was created and has data
        if not os.path.exists(excel_path):
            raise Exception(f"Excel file {excel_path} was not created after save operation!")
        
        # Verify the saved data
        print(f"Verifying saved data...")
        df_verify = pd.read_excel(excel_path, engine='openpyxl')
        if len(df_verify) != len(df_combined):
            raise Exception(f"Data mismatch: expected {len(df_combined)} records, got {len(df_verify)}")
        
        print(f"✅ Feedback saved to {excel_path} successfully! Total records: {len(df_combined)}")
        print(f"✅ Verified: File exists and contains {len(df_verify)} records")
        return True
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error saving to Excel: {error_msg}")
        import traceback
        print("Full traceback:")
        traceback.print_exc()
        # Re-raise the exception so it can be caught and handled properly
        raise Exception(f"Excel save failed: {error_msg}")

def load_feedback_from_excel():
    """Load all feedback data from Excel file"""
    try:
        if os.path.exists(EXCEL_FILE):
            df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
            # Convert categories from string to list if needed
            if 'categories' in df.columns:
                df['categories'] = df['categories'].apply(
                    lambda x: x.split(', ') if isinstance(x, str) and x else []
                )
            return df.to_dict('records')
        else:
            return []
    except Exception as e:
        print(f"Error loading from Excel: {str(e)}")
        return []

# Allowed upload extensions
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Preprocess feedback text
def clean_text(text):
    if pd.isna(text):
        return ''
    return str(text).replace('\n', ' ').strip()


# Advanced feedback analysis and categorization
def categorize_themes(text):
    text_lower = text.lower()
    matched = []
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                matched.append(theme)
                break
    return matched if matched else ['other']

def analyze_feedback(text):
    analyzer = SentimentIntensityAnalyzer()
    vader_result = analyzer.polarity_scores(text)
    compound = vader_result['compound']
    if compound >= 0.05:
        sentiment = 'Positive'
    elif compound <= -0.05:
        sentiment = 'Negative'
    else:
        sentiment = 'Neutral'

    blob = TextBlob(text)
    satisfaction_level = round((blob.sentiment.polarity + 1) * 2.5, 2)  # scale to 0-5
    objectivity = round(1 - blob.sentiment.subjectivity, 2)

    # Theme categorization (advanced)
    themes = categorize_themes(text)
    category = ', '.join(themes)

    # Extract suggestions (NLP: look for improvement phrases)
    suggestion = ''
    for phrase in ['should', 'could', 'improve', 'wish', 'better', 'recommend', 'suggest', 'need', 'must', 'lack']:
        if phrase in text.lower():
            suggestion = text
            break

    return {
        'sentiment': sentiment,
        'satisfaction_level': satisfaction_level,
        'objectivity': objectivity,
        'category': category,
        'themes': themes,
        'suggestion': suggestion
    }

# Actionable insights from feedback DataFrame
def generate_actionable_insights(df):
    # Most common positive/negative themes
    theme_sentiments = defaultdict(list)
    for _, row in df.iterrows():
        for theme in (row.get('themes', '').split(', ') if row.get('themes') else []):
            theme_sentiments[theme].append(row['sentiment'])
    theme_stats = {}
    for theme, sentiments in theme_sentiments.items():
        pos = sentiments.count('Positive')
        neg = sentiments.count('Negative')
        neu = sentiments.count('Neutral')
        total = len(sentiments)
        theme_stats[theme] = {'positive': pos, 'negative': neg, 'neutral': neu, 'total': total}

    # Category-wise satisfaction
    cat_scores = df.groupby('category')['satisfaction'].mean().to_dict()

    # Recommendations
    recommendations = []
    for theme, stats in theme_stats.items():
        if stats['negative'] > 0:
            percent = int(stats['negative'] / stats['total'] * 100)
            recommendations.append(f"Improve {theme} based on {percent}% negative feedback mentioning this.")

    # Standout events
    event_scores = df.groupby('event_name')['satisfaction'].mean()
    if not event_scores.empty:
        best_event = event_scores.idxmax()
        best_score = event_scores.max()
    else:
        best_event = best_score = None

    # Summary report
    summary = {
        'most_common_positive': max(theme_stats.items(), key=lambda x: x[1]['positive'])[0] if theme_stats else None,
        'most_common_negative': max(theme_stats.items(), key=lambda x: x[1]['negative'])[0] if theme_stats else None,
        'category_scores': cat_scores,
        'recommendations': recommendations,
        'standout_event': best_event,
        'standout_score': best_score
    }
    return summary

# Suggestion extraction and ranking
def extract_and_rank_suggestions(df):
    suggestions = df[df['suggestion'] != '']['suggestion'].tolist()
    # Group similar suggestions (simple: lowercase, remove punctuation)
    def normalize(text):
        return re.sub(r'[^a-z0-9 ]', '', text.lower())
    norm_suggestions = [normalize(s) for s in suggestions]
    freq = Counter(norm_suggestions)
    ranked = freq.most_common(10)
    # Map back to original suggestions
    top_suggestions = []
    for norm, count in ranked:
        orig = next((s for s in suggestions if normalize(s) == norm), norm)
        top_suggestions.append({'suggestion': orig, 'count': count})
    return top_suggestions


# --- UPLOAD ROUTE FOR CSV IMPORT ---
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    message = None
    if request.method == 'POST':
        if 'file' not in request.files:
            message = 'No file part'
            return render_template('upload.html', message=message)
        file = request.files['file']
        if file.filename == '':
            message = 'No selected file'
            return render_template('upload.html', message=message)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            df_new = pd.read_csv(file)
            # Expected columns: Event Name, Date, Satisfaction Rating (1-5), What did you like?, Suggestions for Improvement, Overall Comments
            required_cols = ['Event Name', 'Date', 'Satisfaction Rating (1-5)', 'What did you like?', 'Suggestions for Improvement', 'Overall Comments']
            if not all(col in df_new.columns for col in required_cols):
                message = 'CSV missing required columns.'
                return render_template('upload.html', message=message)
            # Clean and preprocess
            df_new['event_name'] = df_new['Event Name'].apply(clean_text)
            df_new['event_date'] = pd.to_datetime(df_new['Date'], errors='coerce').dt.date
            df_new['satisfaction'] = pd.to_numeric(df_new['Satisfaction Rating (1-5)'], errors='coerce').fillna(0).astype(int)
            # Combine feedback fields
            df_new['comments'] = (
                df_new['What did you like?'].fillna('') + ' ' +
                df_new['Suggestions for Improvement'].fillna('') + ' ' +
                df_new['Overall Comments'].fillna('')
            ).apply(clean_text)
            # Analyze each feedback
            analysis_results = df_new['comments'].apply(analyze_feedback)
            df_new['sentiment'] = analysis_results.apply(lambda x: x['sentiment'])
            df_new['satisfaction_level'] = analysis_results.apply(lambda x: x['satisfaction_level'])
            df_new['objectivity'] = analysis_results.apply(lambda x: x['objectivity'])
            df_new['category'] = analysis_results.apply(lambda x: x['category'])
            df_new['suggestion'] = analysis_results.apply(lambda x: x['suggestion'])
            # Insert processed feedback - use Supabase if available, otherwise Excel
            imported_count = 0
            
            if supabase is not None:
                try:
                    # Try to insert into Supabase
                    for _, row in df_new.iterrows():
                        event_name = row['event_name']
                        event_date = row['event_date']
                        # Ensure event exists or insert it
                        event_resp = supabase.table('events').select('id').eq('name', event_name).eq('date', str(event_date)).execute()
                        if event_resp.data:
                            event_id = event_resp.data[0]['id']
                        else:
                            new_event = {
                                'name': event_name,
                                'event_type': 'uploaded_csv',
                                'date': str(event_date),
                                'department': 'General'
                            }
                            insert_event = supabase.table('events').insert(new_event).execute()
                            event_id = insert_event.data[0]['id']
                        # Prepare and insert feedback row
                        feedback_row = {
                            'event_id': event_id,
                            'year_of_study': 'N/A',
                            'satisfaction_rating': row['satisfaction'],
                            'liked': row.get('What did you like?', ''),
                            'suggestions': row.get('Suggestions for Improvement', ''),
                            'comments': row.get('Overall Comments', ''),
                            'sentiment': row['sentiment'],
                            'satisfaction_level': row['satisfaction_level'],
                            'categories': row['category'].split(', ') if isinstance(row['category'], str) else []
                        }
                        supabase.table('feedback').insert(feedback_row).execute()
                        imported_count += 1
                except Exception as e:
                    print(f"Error inserting to Supabase: {str(e)}")
                    # Fall back to Excel
            
            # Save to Excel (either as primary storage or as backup)
            if imported_count == 0 or supabase is None:
                # Save all rows to Excel
                for _, row in df_new.iterrows():
                    feedback_data = {
                        'event_name': row['event_name'],
                        'event_date': str(row['event_date']),
                        'event_type': 'uploaded_csv',
                        'department': 'General',
                        'year_of_study': 'N/A',
                        'satisfaction_rating': row['satisfaction'],
                        'liked': row.get('What did you like?', ''),
                        'suggestions': row.get('Suggestions for Improvement', ''),
                        'comments': row.get('Overall Comments', ''),
                        'categories': row.get('category', ''),
                        'sentiment': row['sentiment'],
                        'satisfaction_level': row['satisfaction_level'],
                        'objectivity': row.get('objectivity', ''),
                        'category': row.get('category', '')
                    }
                    if save_feedback_to_excel(feedback_data):
                        imported_count += 1
            # Aggregate data for summary display (fetch from Supabase or Excel)
            agg = pd.DataFrame()
            if supabase is not None:
                try:
                    agg_resp = supabase.table('feedback').select('satisfaction_rating, event_id, events(name)').execute()
                    agg_df = pd.DataFrame(agg_resp.data)
                    agg_df['event_name'] = agg_df['events'].apply(lambda x: x['name'] if isinstance(x, dict) and 'name' in x else str(x))
                    agg = agg_df.groupby('event_name').agg(
                        satisfaction=('satisfaction_rating', 'mean'),
                        responses=('satisfaction_rating', 'count')
                    ).reset_index()
                except Exception as e:
                    print(f"Error fetching from Supabase: {str(e)}")
            
            # If no Supabase data, use Excel data
            if agg.empty:
                feedback_data = load_feedback_from_excel()
                if feedback_data:
                    df_feedback = pd.DataFrame(feedback_data)
                    if 'event_name' in df_feedback.columns and 'satisfaction_rating' in df_feedback.columns:
                        agg = df_feedback.groupby('event_name').agg(
                            satisfaction=('satisfaction_rating', 'mean'),
                            responses=('satisfaction_rating', 'count')
                        ).reset_index()
            
            agg['sentiment'] = 'Positive'  # Dummy sentiment for now
            
            storage_type = "Supabase" if supabase is not None and imported_count > 0 else "Excel file"
            message = f"Upload successful! Imported {imported_count} feedback entries to {storage_type} ({EXCEL_FILE})."
            agg_dict = agg.to_dict(orient='records') if not agg.empty else []
            return render_template('upload.html', message=message, agg=agg_dict)
        else:
            message = 'Invalid file type. Please upload a CSV.'
    return render_template('upload.html', message=message)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        event_name = request.form.get('event_name')
        event_date = request.form.get('event_date')
        satisfaction = int(request.form.get('satisfaction', 0))
        liked = request.form.get('liked', '')
        suggestions = request.form.get('suggestions', '')
        comments = request.form.get('comments', '')
        department = request.form.get('department', '')
        year_of_study = request.form.get('year_of_study', '')
        event_type = request.form.get('event_type', '')
        categories = request.form.getlist('categories')

        if not event_name or not event_date:
            return render_template('index.html', error='Please fill in all required fields.'), 400

        # Use all feedback text for analysis
        feedback_text = f"{liked} {suggestions} {comments}".strip()
        analysis = analyze_feedback(feedback_text)

        # Prepare feedback data for saving
        feedback_data = {
            'event_name': event_name,
            'event_date': str(event_date),
            'event_type': event_type or 'other',
            'department': department or 'General',
            'year_of_study': year_of_study,
            'satisfaction_rating': satisfaction,
            'liked': liked,
            'suggestions': suggestions,
            'comments': comments,
            'categories': ', '.join(categories) if categories else '',
            'sentiment': analysis['sentiment'],
            'satisfaction_level': analysis['satisfaction_level'],
            'objectivity': analysis.get('objectivity', ''),
            'category': analysis.get('category', '')
        }
        
        # Save to BOTH Excel AND Supabase independently
        print(f"\n{'='*50}")
        print(f"SAVING FEEDBACK DATA")
        print(f"Event: {event_name}, Date: {event_date}")
        print(f"{'='*50}\n")
        
        # Initialize save status
        excel_saved = False
        supabase_saved = False
        excel_error = None
        supabase_error = None
        
        # Save to Excel (ALWAYS attempt, even if Supabase is available)
        print(f"📁 Saving to Excel: {EXCEL_FILE}")
        try:
            excel_saved = save_feedback_to_excel(feedback_data)
            if excel_saved:
                print(f"✅ Excel save: SUCCESS")
            else:
                excel_error = "Excel save function returned False without error details"
                print(f"❌ Excel save: FAILED - {excel_error}")
        except Exception as e:
            excel_error = str(e)
            print(f"❌ Excel save error: {excel_error}")
            import traceback
            traceback.print_exc()
        
        # Save to Supabase (if available)
        if supabase is not None:
            print(f"💾 Saving to Supabase...")
            try:
                # Get or create event
                event_resp = supabase.table('events').select('id').eq('name', event_name).eq('date', event_date).execute()
                if event_resp.data:
                    event_id = event_resp.data[0]['id']
                else:
                    new_event = {
                        'name': event_name,
                        'event_type': event_type or 'other',
                        'date': event_date,
                        'department': department or 'General'
                    }
                    insert_event = supabase.table('events').insert(new_event).execute()
                    event_id = insert_event.data[0]['id']

                # Insert feedback
                feedback_row = {
                    'event_id': event_id,
                    'year_of_study': year_of_study,
                    'satisfaction_rating': satisfaction,
                    'liked': liked,
                    'suggestions': suggestions,
                    'comments': comments,
                    'categories': categories,
                    'sentiment': analysis['sentiment'],
                    'satisfaction_level': analysis['satisfaction_level']
                }
                supabase.table('feedback').insert(feedback_row).execute()
                supabase_saved = True
                print(f"✅ Supabase save: SUCCESS")
            except Exception as db_error:
                supabase_error = str(db_error)
                print(f"❌ Supabase save error: {supabase_error}")
        else:
            print(f"⚠️ Supabase not configured - skipping database save")
        
        # Prepare success message
        save_message = ""
        if excel_saved and supabase_saved:
            save_message = f"✅ Feedback saved to BOTH Supabase database AND Excel file ({EXCEL_FILE}) successfully!"
        elif excel_saved and supabase is not None:
            save_message = f"✅ Feedback saved to Excel file ({EXCEL_FILE}). ⚠️ Supabase save failed: {supabase_error}"
        elif excel_saved:
            save_message = f"✅ Feedback saved to Excel file ({EXCEL_FILE}) successfully! (Supabase not configured)"
        else:
            error_msg = excel_error if excel_error else "Unknown error - check server logs for details"
            save_message = f"❌ Failed to save feedback! Excel error: {error_msg}"
            print(f"❌ CRITICAL: Excel save failed. Error: {error_msg}")
            return render_template('results.html', 
                                 error=f'Failed to save feedback to Excel file. Error: {error_msg}. Please check server logs.', 
                                 save_message=save_message, **analysis), 500

        return render_template('results.html', save_message=save_message, **analysis)
    except Exception as e:
        print(f"Error in analyze route: {str(e)}")
        import traceback
        traceback.print_exc()
        return render_template('index.html', error=f'An error occurred: {str(e)}'), 500

@app.route('/dashboard')
def dashboard():
    # Fetch all feedback and event data - use Supabase if available, otherwise Excel
    feedback_data = []
    
    if supabase is not None:
        try:
            feedback_resp = supabase.table('feedback').select('*').execute()
            feedback_data = feedback_resp.data if feedback_resp.data else []
        except Exception as e:
            print(f"Error fetching from Supabase: {str(e)}")
            # Fall back to Excel
            feedback_data = load_feedback_from_excel()
    else:
        # Load from Excel file
        feedback_data = load_feedback_from_excel()
    
    if not feedback_data:
        return render_template('dashboard.html',
            total_responses=0,
            avg_satisfaction=0,
            pos_percent=0,
            sentiment_bar=None,
            category_pie=None,
            satisfaction_line=None,
            event_bar=None,
            satisfaction_histogram=None,
            department_bar=None,
            suggestions=[]
        )

    # Convert feedback data to DataFrame
    df = pd.DataFrame(feedback_data)

    # If event info is needed, fetch events (not used in current dashboard logic)
    # events_resp = supabase.table('events').select('*').execute()
    # events_data = events_resp.data if events_resp.data else []

    # Metrics
    total_responses = len(df)
    # Use satisfaction_rating if present, else fallback to 'satisfaction'
    if 'satisfaction_rating' in df.columns:
        avg_satisfaction = round(df['satisfaction_rating'].astype(float).mean(), 2)
    elif 'satisfaction' in df.columns:
        avg_satisfaction = round(df['satisfaction'].astype(float).mean(), 2)
    else:
        avg_satisfaction = 0

    pos_percent = 0
    if 'sentiment' in df.columns and total_responses > 0:
        pos_percent = round((df['sentiment'] == 'Positive').sum() / total_responses * 100, 2)

    # Sentiment distribution
    sentiment_bar = None
    if 'sentiment' in df.columns:
        sentiment_counts = df['sentiment'].value_counts().reindex(['Positive', 'Negative', 'Neutral'], fill_value=0)
        fig_sentiment = go.Figure([
            go.Bar(
                x=sentiment_counts.index, 
                y=sentiment_counts.values, 
                marker_color=['#10B981','#EF4444','#6B7280'],
                text=sentiment_counts.values,
                textposition='auto'
            )
        ], layout=go.Layout(
            title='Sentiment Distribution',
            xaxis_title='Sentiment',
            yaxis_title='Number of Responses',
            height=300,
            showlegend=False
        ))
        sentiment_bar = plotly.io.to_json(fig_sentiment)

    # Category pie chart
    category_pie = None
    if 'category' in df.columns:
        category_counts = df['category'].value_counts()
        fig_category = go.Figure([
            go.Pie(labels=category_counts.index, values=category_counts.values, hole=0.3)
        ], layout=go.Layout(title='Feedback Categories', height=300))
        category_pie = plotly.io.to_json(fig_category)

    # Satisfaction Over Time (Line Chart)
    satisfaction_line = None
    if 'event_date' in df.columns and 'satisfaction_rating' in df.columns:
        try:
            df['event_date'] = pd.to_datetime(df['event_date'], errors='coerce')
            df_time = df.dropna(subset=['event_date', 'satisfaction_rating'])
            if not df_time.empty:
                df_time = df_time.sort_values('event_date')
                df_time['date_group'] = df_time['event_date'].dt.date
                satisfaction_by_date = df_time.groupby('date_group')['satisfaction_rating'].mean().reset_index()
                fig_line = go.Figure([
                    go.Scatter(
                        x=satisfaction_by_date['date_group'],
                        y=satisfaction_by_date['satisfaction_rating'],
                        mode='lines+markers',
                        name='Average Satisfaction',
                        line=dict(color='#3B82F6', width=3),
                        marker=dict(size=8, color='#3B82F6')
                    )
                ], layout=go.Layout(
                    title='Satisfaction Trend Over Time',
                    xaxis_title='Date',
                    yaxis_title='Average Satisfaction Rating',
                    height=300,
                    showlegend=False
                ))
                satisfaction_line = plotly.io.to_json(fig_line)
        except Exception as e:
            print(f"Error creating satisfaction line chart: {e}")

    # Event-wise Satisfaction (Bar Chart)
    event_bar = None
    if 'event_name' in df.columns and 'satisfaction_rating' in df.columns:
        try:
            event_satisfaction = df.groupby('event_name')['satisfaction_rating'].agg(['mean', 'count']).reset_index()
            event_satisfaction.columns = ['event_name', 'avg_satisfaction', 'count']
            event_satisfaction = event_satisfaction.sort_values('avg_satisfaction', ascending=False).head(10)
            fig_event = go.Figure([
                go.Bar(
                    x=event_satisfaction['event_name'],
                    y=event_satisfaction['avg_satisfaction'],
                    text=event_satisfaction['avg_satisfaction'].round(2),
                    textposition='auto',
                    marker=dict(color='#10B981', line=dict(color='#059669', width=1.5)),
                    name='Average Satisfaction'
                )
            ], layout=go.Layout(
                title='Top Events by Satisfaction',
                xaxis_title='Event Name',
                yaxis_title='Average Satisfaction Rating',
                height=300,
                showlegend=False,
                xaxis=dict(tickangle=-45)
            ))
            event_bar = plotly.io.to_json(fig_event)
        except Exception as e:
            print(f"Error creating event bar chart: {e}")

    # Satisfaction Rating Distribution (Histogram)
    satisfaction_histogram = None
    if 'satisfaction_rating' in df.columns:
        try:
            fig_hist = go.Figure([
                go.Histogram(
                    x=df['satisfaction_rating'],
                    nbinsx=5,
                    marker=dict(color='#F59E0B', line=dict(color='#D97706', width=1)),
                    name='Rating Distribution'
                )
            ], layout=go.Layout(
                title='Satisfaction Rating Distribution',
                xaxis_title='Satisfaction Rating (1-5)',
                yaxis_title='Number of Responses',
                height=300,
                showlegend=False
            ))
            satisfaction_histogram = plotly.io.to_json(fig_hist)
        except Exception as e:
            print(f"Error creating satisfaction histogram: {e}")

    # Department-wise Analysis (Bar Chart)
    department_bar = None
    if 'department' in df.columns and 'satisfaction_rating' in df.columns:
        try:
            dept_data = df.groupby('department')['satisfaction_rating'].mean().reset_index()
            dept_data = dept_data.sort_values('satisfaction_rating', ascending=False)
            fig_dept = go.Figure([
                go.Bar(
                    x=dept_data['department'],
                    y=dept_data['satisfaction_rating'],
                    text=dept_data['satisfaction_rating'].round(2),
                    textposition='auto',
                    marker=dict(color='#8B5CF6', line=dict(color='#7C3AED', width=1.5)),
                    name='Average Satisfaction'
                )
            ], layout=go.Layout(
                title='Department-wise Satisfaction',
                xaxis_title='Department',
                yaxis_title='Average Satisfaction Rating',
                height=300,
                showlegend=False,
                xaxis=dict(tickangle=-45)
            ))
            department_bar = plotly.io.to_json(fig_dept)
        except Exception as e:
            print(f"Error creating department chart: {e}")

    # Top suggestions (ranked, as objects with suggestion/count)
    suggestions = []
    if 'suggestion' in df.columns:
        suggestions = extract_and_rank_suggestions(df)[:5]
    elif 'suggestions' in df.columns:
        # If suggestions is a list/array, flatten and filter
        suggestions_col = df['suggestions']
        if suggestions_col.apply(lambda x: isinstance(x, list)).any():
            all_suggestions = [item for sublist in suggestions_col if isinstance(sublist, list) for item in sublist]
            # Create a DataFrame to use extract_and_rank_suggestions
            temp_df = pd.DataFrame({'suggestion': all_suggestions})
            suggestions = extract_and_rank_suggestions(temp_df)[:5]
        else:
            temp_df = pd.DataFrame({'suggestion': suggestions_col[suggestions_col != ''].tolist()})
            suggestions = extract_and_rank_suggestions(temp_df)[:5]

    return render_template('dashboard.html',
        total_responses=total_responses,
        avg_satisfaction=avg_satisfaction,
        pos_percent=pos_percent,
        sentiment_bar=sentiment_bar,
        category_pie=category_pie,
        satisfaction_line=satisfaction_line,
        event_bar=event_bar,
        satisfaction_histogram=satisfaction_histogram,
        department_bar=department_bar,
        suggestions=suggestions
    )

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('index.html', error='The requested page was not found.'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('index.html', error='An internal server error occurred.'), 500

# Export for Vercel serverless
# Vercel requires the app to be available as a module-level variable
# Make sure app is at module level so Vercel can import it
if __name__ == '__main__':
    app.run(debug=True)

# For Vercel serverless deployment - app must be exported at module level
# The @vercel/python builder automatically detects Flask apps named 'app'
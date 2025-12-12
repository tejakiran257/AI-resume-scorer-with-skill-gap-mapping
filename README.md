# AI Resume Scorer - Flask

1. Create & activate a Python venv:
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate

2. Install dependencies:
   pip install -r requirements.txt

3. Download spaCy model & NLTK:
   python -m spacy download en_core_web_sm
   python -m nltk.downloader punkt stopwords

4. Security: Revoke any exposed Google API keys in the Cloud Console. Create a new key.
   Do NOT paste keys into code or chat.

5. Set environment variables:
   # Linux / macOS:
   export GOOGLE_API_KEY="YOUR_NEW_KEY"
   export FLASK_SECRET="some-secret-string"
   # Windows (PowerShell):
   setx GOOGLE_API_KEY "YOUR_NEW_KEY"
   setx FLASK_SECRET "some-secret-string"

6. Create demo users:
   flask create-demo-users

7. Run:
   python app.py

8. Open:
   http://127.0.0.1:5000/

Demo accounts:
- jobseeker@example.com / seeker123
- recruiter@example.com / recruit123
Drive Link:
https://drive.google.com/drive/folders/1qb443v_oSW0L74TunbAY8BywVvNWD0ho


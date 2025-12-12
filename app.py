# app.py - Full AI Resume Scorer (updated: Jinja globals exposed)
import os
import re
import json
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for, flash, send_from_directory)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin

# Optional docx extractor
try:
    import docx
except Exception:
    docx = None

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev-secret-please-change")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXT = {"txt", "docx"}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "index"

# ------------------------------------------------------
# FIX: Make Python built-in functions available in Jinja
# ------------------------------------------------------
app.jinja_env.globals.update(enumerate=enumerate)
app.jinja_env.globals.update(len=len)
app.jinja_env.globals.update(str=str)

# Load skills from file
SKILLS_FILE = os.path.join(BASE_DIR, "skills.json")
if os.path.exists(SKILLS_FILE):
    with open(SKILLS_FILE, "r", encoding="utf-8") as f:
        SKILLS = [s.lower() for s in json.load(f)]
else:
    SKILLS = [
        "python","flask","django","react","javascript","aws","docker",
        "kubernetes","sql","pandas","numpy","tensorflow","pytorch","nlp","machine learning"
    ]

# ---------------- Models ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(220), unique=True, nullable=False)
    password_hash = db.Column(db.String(300), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # seeker or recruiter
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(300), nullable=False)
    text = db.Column(db.Text, nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    # create demo users
    if not User.query.filter_by(email="jobseeker@example.com").first():
        db.session.add(User(email="jobseeker@example.com", password_hash=generate_password_hash("seeker123"), role="seeker"))
    if not User.query.filter_by(email="recruiter@example.com").first():
        db.session.add(User(email="recruiter@example.com", password_hash=generate_password_hash("recruit123"), role="recruiter"))
    db.session.commit()

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

# ---------------- Helpers ----------------
def allowed_file(fn):
    return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_EXT

def extract_text_from_docx(path):
    if not docx:
        return ""
    try:
        d = docx.Document(path)
        return "\n".join([p.text for p in d.paragraphs])
    except Exception:
        return ""

def extract_text_from_file(path, original_filename):
    ext = original_filename.rsplit(".",1)[1].lower()
    try:
        if ext == "txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == "docx":
            return extract_text_from_docx(path)
    except Exception:
        return ""
    return ""

def normalize_text(t):
    return re.sub(r"\s+"," ", (t or "").lower()).strip()

def extract_skills(text):
    t = normalize_text(text)
    found = set()
    for s in SKILLS:
        if s in t:
            found.add(s)
    return sorted(found)

def tokenize(text):
    text = normalize_text(text)
    return re.findall(r"[a-z0-9\+]+", text)

def tf_vector(tokens):
    v={}
    for t in tokens:
        v[t]=v.get(t,0)+1
    return v

def cosine_sim(a,b):
    ta = tf_vector(tokenize(a))
    tb = tf_vector(tokenize(b))
    dot = sum(ta.get(k,0)*tb.get(k,0) for k in ta)
    import math
    na = math.sqrt(sum(v*v for v in ta.values()))
    nb = math.sqrt(sum(v*v for v in tb.values()))
    if na==0 or nb==0:
        return 0.0
    return dot/(na*nb)

def compute_score(jd_text, resume_text, jd_sk, res_sk):
    jdset = set([s.lower() for s in jd_sk])
    resset = set([s.lower() for s in res_sk])
    match = len(jdset & resset)
    jdcount = max(1, len(jdset))
    skill_ratio = match / jdcount
    sem = cosine_sim(jd_text, resume_text)
    score = 0.65*skill_ratio + 0.35*sem
    return round(score*100,1), round(skill_ratio*100,1), round(sem*100,1)

def suggested_roadmap(missing, months=3):
    months = max(1,min(24,int(months)))
    base = [
        "Polish resume bullets — highlight measurable impact.",
        "Build a small project demonstrating the required skill.",
        "Practice interview questions (STAR method)."
    ]
    roadmap = {m:[] for m in range(1, months+1)}
    for i,b in enumerate(base):
        roadmap[min(months,1+i)].append(b)
    for i,sk in enumerate(missing):
        roadmap[1 + (i % months)].append(f"Learn & build project for: {sk}")
    return roadmap

def job_suggestions_from_skills(skills):
    s = set([x.lower() for x in skills])
    jobs = set()
    if s & {"python","django","flask","sql"}: jobs.add("Backend Developer (Python)")
    if s & {"react","javascript","html","css"}: jobs.add("Frontend Developer (React)")
    if s & {"pandas","numpy","data"}: jobs.add("Data Analyst / Jr Data Scientist")
    if s & {"aws","docker","kubernetes"}: jobs.add("DevOps / Cloud Engineer (Junior)")
    if not jobs: jobs.add("Software Engineer (General)")
    return sorted(list(jobs))

def ats_checks(text):
    t = (text or "").lower()
    checks=[]
    checks.append(("email", bool(re.search(r"[a-z0-9.\-_]+@[a-z0-9.\-]+\.[a-z]{2,}", t))))
    checks.append(("phone", bool(re.search(r"\+?\d[\d\-\s]{7,}\d", t))))
    for sec in ["experience","education","skills","projects"]:
        checks.append((f"sec_{sec}", sec in t))
    checks.append(("length", len(text or "") >= 200))
    return checks

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template("index.html")

# Registration & login
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        email = request.form.get("email","").strip().lower()
        pwd = request.form.get("password","")
        role = request.form.get("role","seeker")
        if not email or not pwd:
            flash("Please complete all fields", "danger"); return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email already exists", "warning"); return redirect(url_for("register"))
        db.session.add(User(email=email, password_hash=generate_password_hash(pwd), role=role))
        db.session.commit()
        flash("Registered successfully — please login", "success")
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login/seeker")
def login_seeker():
    return render_template("login_seeker.html")

@app.route("/login/recruiter")
def login_recruiter():
    return render_template("login_recruiter.html")

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email","").strip().lower()
    pwd = request.form.get("password","")
    role = request.form.get("role","")
    if not email or not pwd or role not in ("seeker","recruiter"):
        flash("Invalid login data", "danger"); return redirect(url_for("index"))
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, pwd) or user.role != role:
        flash("Invalid credentials", "danger"); return redirect(url_for("index"))
    login_user(user)
    flash("Welcome!", "success")
    return redirect(url_for("seeker_dashboard") if user.role=="seeker" else url_for("recruiter_dashboard"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("index"))

# Seeker: upload resumes
@app.route("/seeker", methods=["GET","POST"])
@login_required
def seeker_dashboard():
    if current_user.role!="seeker":
        flash("Access denied", "danger"); return redirect(url_for("index"))
    if request.method=="POST":
        f = request.files.get("resume_file")
        if not f or not f.filename:
            flash("Choose a file", "warning"); return redirect(url_for("seeker_dashboard"))
        if not allowed_file(f.filename):
            flash("Unsupported file type. Use .txt or .docx", "danger"); return redirect(url_for("seeker_dashboard"))
        original = secure_filename(f.filename)
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        stored = f"{current_user.id}_{ts}_{original}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], stored)
        f.save(path)
        text = extract_text_from_file(path, original)
        r = Resume(filename=stored, original_filename=original, text=text, uploaded_by=current_user.id)
        db.session.add(r); db.session.commit()
        flash("Uploaded successfully", "success")
        return redirect(url_for("seeker_dashboard"))
    resumes = Resume.query.filter_by(uploaded_by=current_user.id).order_by(Resume.uploaded_at.desc()).all()
    return render_template("seeker.html", resumes=resumes)

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

# Recruiter dashboard (match JD -> resumes)
@app.route("/recruiter")
@login_required
def recruiter_dashboard():
    if current_user.role!="recruiter":
        flash("Access denied", "danger"); return redirect(url_for("index"))
    recent = Resume.query.order_by(Resume.uploaded_at.desc()).limit(10).all()
    return render_template("recruiter.html", recent=recent)

def read_text_from_upload_fileobj(f):
    filename = f.filename or ""
    ext = filename.rsplit(".",1)[-1].lower() if "." in filename else ""
    if ext=="txt":
        try:
            return f.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""
    elif ext=="docx":
        tmp = os.path.join(app.config["UPLOAD_FOLDER"], "tmp_" + secure_filename(filename))
        f.save(tmp)
        txt = extract_text_from_file(tmp, filename)
        try: os.remove(tmp)
        except: pass
        return txt
    else:
        try:
            return f.read().decode("utf-8", errors="ignore")
        except:
            return ""

@app.route("/recruiter/match_jd", methods=["GET","POST"])
@login_required
def recruiter_match_jd():
    if current_user.role!="recruiter":
        flash("Access denied", "danger"); return redirect(url_for("index"))
    results=None; jd_text=""
    if request.method=="POST":
        jd_text = request.form.get("jd_text","").strip()
        jd_file = request.files.get("jd_file")
        if not jd_text and jd_file and jd_file.filename:
            jd_text = read_text_from_upload_fileobj(jd_file)
        if not jd_text:
            flash("Please paste a Job Description or upload a .txt/.docx JD file.", "warning")
            return redirect(url_for("recruiter_dashboard"))
        rows=[]
        resumes = Resume.query.order_by(Resume.uploaded_at.desc()).all()
        for r in resumes:
            resume_text = r.text or ""
            jd_sk = extract_skills(jd_text)
            res_sk = extract_skills(resume_text)
            missing = sorted(list(set(jd_sk) - set(res_sk)))
            score, skill_pct, sem_pct = compute_score(jd_text, resume_text, jd_sk, res_sk)
            rows.append({
                "rid": r.id,
                "filename": r.original_filename,
                "uploader": User.query.get(r.uploaded_by).email if r.uploaded_by else "Unknown",
                "score": score,
                "skill_pct": skill_pct,
                "semantic_pct": sem_pct,
                "missing": missing,
                "res_sk": res_sk,
                "uploaded_at": r.uploaded_at
            })
        rows.sort(key=lambda x: x["score"], reverse=True)
        results = rows
    return render_template("recruiter_match.html", results=results, jd_text=jd_text)

# Recruiter view + analyze single resume
@app.route("/recruiter/resume/<int:rid>", methods=["GET","POST"])
@login_required
def recruiter_view_resume(rid):
    if current_user.role!="recruiter":
        flash("Access denied", "danger"); return redirect(url_for("index"))
    r = Resume.query.get_or_404(rid)
    uploader = User.query.get(r.uploaded_by) if r.uploaded_by else None
    if request.method=="POST":
        jd_text = request.form.get("jd_text","").strip()
        months = int(request.form.get("months","3") or 3)
        resume_text = r.text or ""
        jd_sk = extract_skills(jd_text) if jd_text else []
        res_sk = extract_skills(resume_text)
        missing = sorted(list(set(jd_sk) - set(res_sk)))
        extra = sorted(list(set(res_sk) - set(jd_sk)))
        ats = ats_checks(resume_text)
        score, skill_pct, sem_pct = compute_score(jd_text, resume_text, jd_sk, res_sk)
        timeline = suggested_roadmap(missing, months=months)
        jobs = job_suggestions_from_skills(res_sk)
        result = {"score":score,"skill_pct":skill_pct,"semantic_pct":sem_pct,"jd_sk":jd_sk,"res_sk":res_sk,"missing":missing,"extra":extra,"ats":ats,"timeline":timeline,"jobs":jobs,"months":months,"rid":rid,"filename":r.original_filename,"resume_text":resume_text,"jd_text":jd_text}
        return render_template("recruiter_resume_view.html", r=r, uploader=uploader, result=result)
    return render_template("recruiter_resume_view.html", r=r, uploader=uploader, result=None)

@app.route("/recruiter/download/<int:rid>")
@login_required
def recruiter_download(rid):
    if current_user.role!="recruiter":
        flash("Access denied", "danger"); return redirect(url_for("index"))
    r = Resume.query.get_or_404(rid)
    return send_from_directory(app.config["UPLOAD_FOLDER"], r.filename, as_attachment=True, download_name=r.original_filename)

# analyze stored resume (seeker flow or recruiter deep analyze)
@app.route("/analyze/stored/<int:rid>", methods=["GET","POST"])
@login_required
def analyze_stored(rid):
    r = Resume.query.get_or_404(rid)
    if request.method=="POST":
        jd_text = request.form.get("jd_text","").strip()
        months = int(request.form.get("months","3") or 3)
        resume_text = r.text or ""
        jd_sk = extract_skills(jd_text) if jd_text else []
        res_sk = extract_skills(resume_text)
        missing = sorted(list(set(jd_sk) - set(res_sk)))
        ats = ats_checks(resume_text)
        score, skill_pct, sem_pct = compute_score(jd_text, resume_text, jd_sk, res_sk)
        roadmap = suggested_roadmap(missing, months=months)
        jobs = job_suggestions_from_skills(res_sk)
        result = {"score":score,"skill_pct":skill_pct,"semantic_pct":sem_pct,"jd_sk":jd_sk,"res_sk":res_sk,"missing":missing,"ats":ats,"roadmap":roadmap,"jobs":jobs,"rid":rid,"filename":r.original_filename,"months":months,"resume_text":resume_text,"jd_text":jd_text}
        return render_template("results.html", result=result)
    uploader = User.query.get(r.uploaded_by) if r.uploaded_by else None
    return render_template("analyze_stored.html", r=r, uploader=uploader)

# route map, jobs, ats pages
@app.route("/route-map/<int:rid>/<int:months>")
@login_required
def route_map(rid, months):
    r = Resume.query.get_or_404(rid)
    missing = extract_skills(r.text or "")
    timeline = suggested_roadmap(missing, months=months)
    return render_template("route_map.html", resume=r, timeline=timeline, months=months)

@app.route("/job-suggestions/<int:rid>")
@login_required
def job_suggestions(rid):
    r = Resume.query.get_or_404(rid)
    suggestions = job_suggestions_from_skills(extract_skills(r.text or ""))
    return render_template("job_suggestions.html", resume=r, suggestions=suggestions)

@app.route("/ats-improvement/<int:rid>")
@login_required
def ats_improvement(rid):
    r = Resume.query.get_or_404(rid)
    improvements = [
        "Add clear headings: Experience, Education, Skills, Projects",
        "Avoid images and tables; use plain text",
        "Add measurable bullets (e.g., improved X by 20%)",
        "Place contact details at top in plain text"
    ]
    return render_template("ats_improvement.html", resume=r, improvements=improvements)

if __name__ == "__main__":
    app.run(debug=True)

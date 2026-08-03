from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os, json, uuid, smtplib, re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

app = Flask(__name__)
app.config['SECRET_KEY'] = 'crms-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///crimes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'mp4', 'mov'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── Models ──────────────────────────────────────────────
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='citizen')
    is_active = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports = db.relationship('CrimeReport', backref='reporter', lazy=True, foreign_keys='CrimeReport.user_id')

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class CrimeReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    crime_type = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    incident_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(30), default='Pending')
    priority = db.Column(db.String(20), default='Medium')
    assigned_officer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_officer = db.relationship('User', foreign_keys=[assigned_officer_id])
    anonymous = db.Column(db.Boolean, default=False)
    ai_flag_score = db.Column(db.Float, default=0.0)
    ai_flagged = db.Column(db.Boolean, default=False)
    ai_flag_reasons = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    evidence = db.relationship('Evidence', backref='report', lazy=True, cascade='all, delete-orphan')
    updates = db.relationship('CaseUpdate', backref='report', lazy=True, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='report', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='report', lazy=True, cascade='all, delete-orphan', order_by='ChatMessage.created_at')

class Evidence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('crime_report.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200))
    file_type = db.Column(db.String(50))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class CaseUpdate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('crime_report.id'), nullable=False)
    officer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    officer = db.relationship('User', foreign_keys=[officer_id])
    message = db.Column(db.Text, nullable=False)
    status_change = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    report_id = db.Column(db.Integer, db.ForeignKey('crime_report.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_emergency = db.Column(db.Boolean, default=False)
    emergency_id = db.Column(db.Integer, db.ForeignKey('emergency_alert.id'), nullable=True)
    is_wanted_alert = db.Column(db.Boolean, default=False)
    wanted_id = db.Column(db.Integer, db.ForeignKey('wanted_person.id'), nullable=True)
    is_chat = db.Column(db.Boolean, default=False)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('crime_report.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender = db.relationship('User', foreign_keys=[sender_id])
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmergencyAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', foreign_keys=[user_id])
    alert_type = db.Column(db.String(30), default='General')  # General | Fire | Medical | Violence
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float)
    status = db.Column(db.String(20), default='Active')  # Active | Acknowledged | Resolved
    acknowledged_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    acknowledged_by = db.relationship('User', foreign_keys=[acknowledged_by_id])
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    pings = db.relationship('LocationPing', backref='alert', lazy=True, cascade='all, delete-orphan', order_by='LocationPing.created_at')

class LocationPing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    alert_id = db.Column(db.Integer, db.ForeignKey('emergency_alert.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WantedPerson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    alias = db.Column(db.String(120))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    crime_type = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    last_seen_location = db.Column(db.String(200))
    danger_level = db.Column(db.String(20), default='Medium')  # Low | Medium | High | Extreme
    photo = db.Column(db.String(200))
    reward_info = db.Column(db.String(300))
    status = db.Column(db.String(20), default='Wanted')  # Wanted | Found | Arrested | Cleared
    posted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    posted_by = db.relationship('User', foreign_keys=[posted_by_id])
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])
    resolution_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    notifications = db.relationship('Notification', backref='wanted', lazy=True)

class EmailSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gmail_address = db.Column(db.String(120), nullable=False)
    gmail_app_password = db.Column(db.String(120), nullable=False)
    sender_name = db.Column(db.String(100), default='CRMS Tanzania')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    require_email_verification = db.Column(db.Boolean, default=True)

@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))

def allowed_file(f): return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
def gen_case_number(): return 'CR-' + datetime.now().strftime('%Y%m') + '-' + str(uuid.uuid4())[:6].upper()

# ── AI-Generated Text Heuristic ──────────────────────────
AI_STOCK_PHRASES = [
    'i would like to report', 'i am writing to', 'it is important to note',
    'please be advised', 'rest assured', 'first and foremost', 'in conclusion',
    'in summary', 'on the other hand', 'as a result of', 'furthermore',
    'moreover', 'additionally,', 'notwithstanding', 'it is worth noting',
    'to summarize', 'in light of', 'with that said', 'needless to say',
    'i hope this message finds you well', 'thank you for your attention to this matter'
]
AI_VOCAB = [
    'utilize', 'facilitate', 'endeavor', 'ascertain', 'meticulous', 'meticulously',
    'paramount', 'delve', 'underscore', 'tapestry', 'testament', 'vibrant',
    'landscape', 'boast', 'robust', 'comprehensive', 'myriad', 'plethora',
    'intricate', 'pivotal', 'seamless', 'holistic'
]

def analyze_ai_likelihood(text):
    """Local heuristic triage signal for possibly AI-generated report text.
    Approximate by design — a prompt for human review, not a verdict."""
    text = text or ''
    lower = text.lower()
    score = 0.0
    reasons = []

    phrase_hits = [p for p in AI_STOCK_PHRASES if p in lower]
    if phrase_hits:
        score += min(len(phrase_hits) * 12, 40)
        reasons.append(f'Uses stock AI-style phrasing (e.g. "{phrase_hits[0]}")')

    vocab_hits = [w for w in AI_VOCAB if re.search(rf'\b{w}\b', lower)]
    if vocab_hits:
        score += min(len(vocab_hits) * 8, 25)
        reasons.append(f'Contains AI-favored vocabulary: {", ".join(vocab_hits[:4])}')

    em_dash_count = text.count('—') + text.count(' -- ')
    if em_dash_count >= 2:
        score += min(em_dash_count * 5, 15)
        reasons.append(f'Uses em-dash punctuation {em_dash_count} time(s), uncommon in typed reports')

    sentences = [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if len(s.split()) >= 3]
    if len(sentences) >= 4:
        lengths = [len(s.split()) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        cv = (variance ** 0.5) / mean_len if mean_len else 0
        if cv < 0.35:
            score += 20
            reasons.append('Unusually uniform sentence length/structure throughout the report')

    word_count = len(re.findall(r"\b[\w']+\b", text))
    if word_count >= 40 and not re.search(r"\b\w+'\w+\b", text):
        score += 10
        reasons.append('No contractions or informal phrasing typical of hurried eyewitness accounts')

    score = min(round(score), 100)
    return score, score >= 55, reasons

# ── Email Helper ────────────────────────────────────────
def get_email_settings():
    return EmailSettings.query.first()

def get_system_settings():
    cfg = SystemSettings.query.first()
    if not cfg:
        cfg = SystemSettings(require_email_verification=True)
        db.session.add(cfg); db.session.commit()
    return cfg

def email_verification_enabled():
    return get_system_settings().require_email_verification

def send_email(to_email, subject, html_body):
    cfg = get_email_settings()
    if not cfg:
        return False, 'Email not configured. Admin must set Gmail credentials first.'
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f'{cfg.sender_name} <{cfg.gmail_address}>'
        msg['To'] = to_email
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(cfg.gmail_address, cfg.gmail_app_password)
            server.sendmail(cfg.gmail_address, to_email, msg.as_string())
        return True, 'Email sent successfully.'
    except smtplib.SMTPAuthenticationError:
        return False, 'Gmail authentication failed. Check email and App Password.'
    except Exception as e:
        return False, str(e)

def send_verification_email(user):
    token = serializer.dumps(user.email, salt='email-verify')
    link = url_for('verify_email', token=token, _external=True)
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:580px;margin:auto;background:#0d0f14;color:#e8eaf0;border-radius:12px;overflow:hidden">
      <div style="background:#e8a020;padding:28px 32px;text-align:center">
        <h1 style="color:#000;margin:0;font-size:1.4rem">🛡️ CRMS Tanzania</h1>
        <p style="color:#000;margin:6px 0 0;font-size:.9rem">Crime Reporting & Management System</p>
      </div>
      <div style="padding:36px 32px">
        <h2 style="color:#e8eaf0;margin:0 0 12px">Verify Your Email Address</h2>
        <p style="color:#9099b0;line-height:1.6">Hello <strong style="color:#e8eaf0">{user.full_name}</strong>,</p>
        <p style="color:#9099b0;line-height:1.6">Thank you for registering. Click the button below to verify your email address and activate your account.</p>
        <div style="text-align:center;margin:32px 0">
          <a href="{link}" style="background:#e8a020;color:#000;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:1rem;display:inline-block">✅ Verify My Email</a>
        </div>
        <p style="color:#6070a0;font-size:.85rem">This link expires in <strong>1 hour</strong>. If you did not register, ignore this email.</p>
        <hr style="border:none;border-top:1px solid #2a2f45;margin:24px 0">
        <p style="color:#6070a0;font-size:.8rem">Or copy this link: <a href="{link}" style="color:#e8a020">{link}</a></p>
      </div>
      <div style="background:#141720;padding:16px 32px;text-align:center;color:#6070a0;font-size:.8rem">© 2024 CRMS Tanzania · Tanzania Police Force</div>
    </div>"""
    return send_email(user.email, 'Verify Your CRMS Account', html)

def send_case_update_email(user, report, message):
    status_color = {'Pending':'#e8a020','Under Investigation':'#3080e8','Resolved':'#30c060','Closed':'#6070a0'}.get(report.status,'#9099b0')
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:580px;margin:auto;background:#0d0f14;color:#e8eaf0;border-radius:12px;overflow:hidden">
      <div style="background:#e8a020;padding:28px 32px;text-align:center">
        <h1 style="color:#000;margin:0;font-size:1.4rem">🛡️ CRMS Tanzania</h1>
      </div>
      <div style="padding:36px 32px">
        <h2 style="color:#e8eaf0;margin:0 0 12px">Case Update Notification</h2>
        <p style="color:#9099b0">Hello <strong style="color:#e8eaf0">{user.full_name}</strong>,</p>
        <div style="background:#1a1e2e;border:1px solid #2a2f45;border-radius:8px;padding:20px;margin:20px 0">
          <p style="margin:0 0 8px;font-size:.8rem;color:#6070a0;text-transform:uppercase;letter-spacing:.05em">Case Number</p>
          <p style="margin:0 0 16px;font-family:monospace;color:#e8a020;font-size:1.1rem">{report.case_number}</p>
          <p style="margin:0 0 8px;font-size:.8rem;color:#6070a0;text-transform:uppercase;letter-spacing:.05em">Status</p>
          <span style="background:{status_color}22;color:{status_color};padding:4px 12px;border-radius:100px;font-size:.85rem">{report.status}</span>
        </div>
        <p style="color:#9099b0;line-height:1.6"><strong style="color:#e8eaf0">Update:</strong> {message}</p>
        <div style="text-align:center;margin:28px 0">
          <a href="{url_for('track_case', case_number=report.case_number, _external=True)}" style="background:#e8a020;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700">View Case Details</a>
        </div>
      </div>
      <div style="background:#141720;padding:16px 32px;text-align:center;color:#6070a0;font-size:.8rem">© 2024 CRMS Tanzania</div>
    </div>"""
    return send_email(user.email, f'Case Update: {report.case_number}', html)

# ── Auth ────────────────────────────────────────────────
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(email=request.form['email']).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
        verification_required = email_verification_enabled()
        u = User(full_name=request.form['full_name'], email=request.form['email'],
                 phone=request.form.get('phone',''), email_verified=not verification_required)
        u.set_password(request.form['password'])
        db.session.add(u); db.session.commit()
        if not verification_required:
            flash('Account created! You can now login.', 'success')
            return redirect(url_for('login'))
        # Send verification email
        ok, msg = send_verification_email(u)
        if ok:
            flash('Account created! A verification email has been sent. Please check your inbox.', 'success')
        else:
            flash(f'Account created! However, verification email could not be sent: {msg}. Contact admin.', 'error')
        return redirect(url_for('verify_pending', email=u.email))
    return render_template('register.html')

@app.route('/verify-pending')
def verify_pending():
    email = request.args.get('email','')
    return render_template('verify_pending.html', email=email)

@app.route('/verify/<token>')
def verify_email(token):
    try:
        email = serializer.loads(token, salt='email-verify', max_age=3600)
    except SignatureExpired:
        flash('Verification link has expired. Please register again or request a new link.', 'error')
        return redirect(url_for('login'))
    except BadSignature:
        flash('Invalid verification link.', 'error')
        return redirect(url_for('login'))
    u = User.query.filter_by(email=email).first()
    if not u:
        flash('User not found.', 'error')
        return redirect(url_for('login'))
    if u.email_verified:
        flash('Email already verified. Please login.', 'success')
        return redirect(url_for('login'))
    u.email_verified = True
    db.session.commit()
    flash('Email verified successfully! You can now login.', 'success')
    return redirect(url_for('login'))

@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email','').strip()
    u = User.query.filter_by(email=email).first()
    if u and not u.email_verified:
        ok, msg = send_verification_email(u)
        if ok:
            flash('Verification email resent! Check your inbox.', 'success')
        else:
            flash(f'Could not send email: {msg}', 'error')
    else:
        flash('Account not found or already verified.', 'error')
    return redirect(url_for('verify_pending', email=email))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(email=request.form['email']).first()
        if not u or not u.check_password(request.form['password']):
            flash('Invalid email or password.', 'error')
            return render_template('login.html')
        if not u.is_active:
            flash('Your account has been suspended. Contact admin.', 'error')
            return render_template('login.html')
        if email_verification_enabled() and not u.email_verified:
            flash('Please verify your email before logging in.', 'error')
            return redirect(url_for('verify_pending', email=u.email))
        login_user(u)
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); return redirect(url_for('index'))

# ── Dashboard ───────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role in ('admin', 'officer'):
        reports = CrimeReport.query.order_by(CrimeReport.created_at.desc()).all()
        users = User.query.all()
        stats = {
            'total': len(reports),
            'pending': sum(1 for r in reports if r.status == 'Pending'),
            'investigating': sum(1 for r in reports if r.status == 'Under Investigation'),
            'resolved': sum(1 for r in reports if r.status == 'Resolved'),
            'users': len(users),
            'wanted_active': WantedPerson.query.filter_by(status='Wanted').count(),
            'emergencies_active': EmergencyAlert.query.filter(EmergencyAlert.status != 'Resolved').count(),
            'ai_flagged': sum(1 for r in reports if r.ai_flagged)
        }
        crime_types = {}
        for r in reports:
            crime_types[r.crime_type] = crime_types.get(r.crime_type, 0) + 1
        return render_template('admin_dashboard.html', reports=reports[:10], stats=stats,
                               crime_types=json.dumps(crime_types), users=users)
    else:
        reports = CrimeReport.query.filter_by(user_id=current_user.id).order_by(CrimeReport.created_at.desc()).all()
        notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
        wanted_active = WantedPerson.query.filter_by(status='Wanted').count()
        return render_template('citizen_dashboard.html', reports=reports, notifications=notifs, wanted_active=wanted_active)

# ── Crime Reporting ─────────────────────────────────────
@app.route('/report', methods=['GET','POST'])
@login_required
def report_crime():
    if request.method == 'POST':
        ai_score, ai_flagged, ai_reasons = analyze_ai_likelihood(request.form['description'])
        rpt = CrimeReport(
            case_number=gen_case_number(), user_id=current_user.id,
            crime_type=request.form['crime_type'], description=request.form['description'],
            location=request.form['location'],
            latitude=float(request.form['latitude']) if request.form.get('latitude') else None,
            longitude=float(request.form['longitude']) if request.form.get('longitude') else None,
            incident_date=datetime.strptime(request.form['incident_date'], '%Y-%m-%dT%H:%M'),
            priority=request.form.get('priority','Medium'), anonymous=('anonymous' in request.form),
            ai_flag_score=ai_score, ai_flagged=ai_flagged,
            ai_flag_reasons='; '.join(ai_reasons) if ai_reasons else None
        )
        db.session.add(rpt); db.session.flush()
        for f in request.files.getlist('evidence'):
            if f and f.filename and allowed_file(f.filename):
                fn = secure_filename(f.filename)
                unique_fn = str(uuid.uuid4()) + '_' + fn
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_fn))
                db.session.add(Evidence(report_id=rpt.id, filename=unique_fn, original_name=fn, file_type=f.content_type))
        db.session.commit()
        flash(f'Report submitted! Case Number: {rpt.case_number}', 'success')
        return redirect(url_for('track_case', case_number=rpt.case_number))
    return render_template('report.html')

# ── Case Tracking ────────────────────────────────────────
@app.route('/track')
@login_required
def track():
    return render_template('track.html')

@app.route('/track/<case_number>')
@login_required
def track_case(case_number):
    rpt = CrimeReport.query.filter_by(case_number=case_number).first_or_404()
    if current_user.role == 'citizen' and rpt.user_id != current_user.id:
        flash('Access denied.', 'error'); return redirect(url_for('dashboard'))
    return render_template('case_detail.html', report=rpt)

@app.route('/api/track', methods=['POST'])
@login_required
def api_track():
    cn = request.json.get('case_number','').strip()
    rpt = CrimeReport.query.filter_by(case_number=cn).first()
    if not rpt: return jsonify({'error': 'Case not found'}), 404
    if current_user.role == 'citizen' and rpt.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    return jsonify({'case_number': rpt.case_number, 'status': rpt.status, 'crime_type': rpt.crime_type,
                    'location': rpt.location, 'created_at': rpt.created_at.strftime('%Y-%m-%d')})

# ── Case Discussion (Chat) ────────────────────────────────
def can_access_report(rpt):
    if current_user.role == 'citizen':
        return rpt.user_id == current_user.id
    return current_user.role in ('admin', 'officer')

@app.route('/api/case/<int:rid>/messages')
@login_required
def api_case_messages(rid):
    rpt = CrimeReport.query.get_or_404(rid)
    if not can_access_report(rpt):
        return jsonify({'error': 'Forbidden'}), 403
    msgs = ChatMessage.query.filter_by(report_id=rid).order_by(ChatMessage.created_at).all()
    return jsonify([{
        'id': m.id,
        'message': m.message,
        'sender_name': 'Anonymous Reporter' if (rpt.anonymous and m.sender_id == rpt.user_id and current_user.role in ('admin', 'officer')) else m.sender.full_name,
        'sender_role': m.sender.role,
        'mine': m.sender_id == current_user.id,
        'created_at': m.created_at.strftime('%b %d, %H:%M')
    } for m in msgs])

@app.route('/api/case/<int:rid>/messages', methods=['POST'])
@login_required
def api_case_send_message(rid):
    rpt = CrimeReport.query.get_or_404(rid)
    if not can_access_report(rpt):
        return jsonify({'error': 'Forbidden'}), 403
    text = (request.json or {}).get('message', '').strip()
    if not text:
        return jsonify({'error': 'Message required'}), 400
    msg = ChatMessage(report_id=rid, sender_id=current_user.id, message=text)
    db.session.add(msg)
    sender_label = 'Anonymous Reporter' if (rpt.anonymous and current_user.role == 'citizen') else current_user.full_name
    preview = f'New message on case {rpt.case_number} from {sender_label}: {text[:80]}'
    if current_user.role == 'citizen':
        recipient_ids = [rpt.assigned_officer_id] if rpt.assigned_officer_id else [u.id for u in User.query.filter_by(role='admin', is_active=True).all()]
        for uid in recipient_ids:
            db.session.add(Notification(user_id=uid, report_id=rid, is_chat=True, message=preview))
    else:
        db.session.add(Notification(user_id=rpt.user_id, report_id=rid, is_chat=True, message=preview))
    db.session.commit()
    return jsonify({'ok': True, 'id': msg.id, 'created_at': msg.created_at.strftime('%b %d, %H:%M')})

# ── Admin: Reports ───────────────────────────────────────
@app.route('/admin/reports')
@login_required
def admin_reports():
    if current_user.role not in ('admin','officer'): return redirect(url_for('dashboard'))
    q = request.args.get('q',''); status = request.args.get('status',''); ai_only = request.args.get('ai','')
    query = CrimeReport.query
    if q: query = query.filter(CrimeReport.case_number.contains(q)|CrimeReport.crime_type.contains(q)|CrimeReport.location.contains(q))
    if status: query = query.filter_by(status=status)
    if ai_only == '1': query = query.filter_by(ai_flagged=True)
    reports = query.order_by(CrimeReport.created_at.desc()).all()
    officers = User.query.filter(User.role.in_(['admin','officer'])).all()
    return render_template('admin_reports.html', reports=reports, officers=officers, q=q, status_filter=status, ai_only=ai_only)

@app.route('/admin/report/<int:rid>', methods=['GET','POST'])
@login_required
def admin_report_detail(rid):
    if current_user.role not in ('admin','officer'): return redirect(url_for('dashboard'))
    rpt = CrimeReport.query.get_or_404(rid)
    if request.method == 'POST':
        old_status = rpt.status
        rpt.status = request.form.get('status', rpt.status)
        rpt.priority = request.form.get('priority', rpt.priority)
        oid = request.form.get('assigned_officer_id')
        rpt.assigned_officer_id = int(oid) if oid else None
        rpt.updated_at = datetime.utcnow()
        note = request.form.get('update_message','').strip()
        if note:
            upd = CaseUpdate(report_id=rpt.id, officer_id=current_user.id, message=note,
                             status_change=rpt.status if rpt.status != old_status else None)
            db.session.add(upd)
            notif = Notification(user_id=rpt.user_id, report_id=rpt.id,
                                 message=f'Case {rpt.case_number} updated: {note[:80]}')
            db.session.add(notif)
            db.session.commit()
            # Send email notification to reporter
            if not rpt.anonymous:
                send_case_update_email(rpt.reporter, rpt, note)
        else:
            db.session.commit()
        flash('Case updated.', 'success')
        return redirect(url_for('admin_report_detail', rid=rid))
    officers = User.query.filter(User.role.in_(['admin','officer'])).all()
    return render_template('admin_report_detail.html', report=rpt, officers=officers)

# ── Admin: Users ─────────────────────────────────────────
@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'admin': return redirect(url_for('dashboard'))
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<int:uid>/toggle', methods=['POST'])
@login_required
def toggle_user(uid):
    if current_user.role != 'admin': return jsonify({'error':'Forbidden'}), 403
    u = User.query.get_or_404(uid)
    u.is_active = not u.is_active; db.session.commit()
    return jsonify({'active': u.is_active})

@app.route('/admin/users/<int:uid>/role', methods=['POST'])
@login_required
def change_role(uid):
    if current_user.role != 'admin': return jsonify({'error':'Forbidden'}), 403
    u = User.query.get_or_404(uid)
    u.role = request.json.get('role', u.role); db.session.commit()
    return jsonify({'role': u.role})

# ── Admin: Email Settings ────────────────────────────────
@app.route('/admin/email-settings', methods=['GET','POST'])
@login_required
def admin_email_settings():
    if current_user.role != 'admin': return redirect(url_for('dashboard'))
    cfg = get_email_settings()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save':
            if cfg:
                cfg.gmail_address = request.form['gmail_address'].strip()
                cfg.gmail_app_password = request.form['gmail_app_password'].strip()
                cfg.sender_name = request.form.get('sender_name','CRMS Tanzania').strip()
                cfg.updated_at = datetime.utcnow()
                cfg.updated_by = current_user.id
            else:
                cfg = EmailSettings(
                    gmail_address=request.form['gmail_address'].strip(),
                    gmail_app_password=request.form['gmail_app_password'].strip(),
                    sender_name=request.form.get('sender_name','CRMS Tanzania').strip(),
                    updated_by=current_user.id
                )
                db.session.add(cfg)
            db.session.commit()
            flash('Email settings saved successfully.', 'success')
        elif action == 'test':
            if not cfg:
                flash('Save settings first before testing.', 'error')
            else:
                test_to = request.form.get('test_email', current_user.email).strip()
                html = f"""<div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;background:#0d0f14;color:#e8eaf0;border-radius:12px;overflow:hidden">
                  <div style="background:#e8a020;padding:24px;text-align:center"><h2 style="color:#000;margin:0">🛡️ CRMS Tanzania – Test Email</h2></div>
                  <div style="padding:28px"><p style="color:#9099b0">This is a <strong style="color:#e8eaf0">test email</strong> from your CRMS system.</p>
                  <p style="color:#9099b0">If you received this, your Gmail configuration is working correctly! ✅</p>
                  <p style="color:#6070a0;font-size:.85rem;margin-top:16px">Sent at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p></div></div>"""
                ok, msg = send_email(test_to, 'CRMS Test Email', html)
                if ok:
                    flash(f'Test email sent successfully to {test_to}!', 'success')
                else:
                    flash(f'Test failed: {msg}', 'error')
        return redirect(url_for('admin_email_settings'))
    return render_template('admin_email_settings.html', cfg=cfg, sys_cfg=get_system_settings())

@app.route('/admin/toggle-verification', methods=['POST'])
@login_required
def toggle_email_verification():
    if current_user.role != 'admin': return jsonify({'error':'Forbidden'}), 403
    cfg = get_system_settings()
    cfg.require_email_verification = not cfg.require_email_verification
    db.session.commit()
    return jsonify({'require_email_verification': cfg.require_email_verification})

# ── Wanted Persons ────────────────────────────────────────
def broadcast_wanted_alert(wanted, message):
    users = User.query.filter_by(is_active=True).all()
    for u in users:
        db.session.add(Notification(user_id=u.id, message=message, is_wanted_alert=True, wanted_id=wanted.id))
    db.session.commit()

@app.route('/wanted')
@login_required
def wanted_list():
    q = request.args.get('q', '').strip()
    status = request.args.get('status', 'Wanted')
    query = WantedPerson.query
    if q:
        query = query.filter(WantedPerson.full_name.contains(q) | WantedPerson.alias.contains(q) | WantedPerson.crime_type.contains(q))
    if status:
        query = query.filter_by(status=status)
    people = query.order_by(WantedPerson.created_at.desc()).all()
    return render_template('wanted_list.html', people=people, q=q, status_filter=status)

@app.route('/wanted/new', methods=['GET', 'POST'])
@login_required
def wanted_new():
    if current_user.role not in ('admin', 'officer'):
        return redirect(url_for('wanted_list'))
    if request.method == 'POST':
        wp = WantedPerson(
            full_name=request.form['full_name'].strip(),
            alias=request.form.get('alias', '').strip() or None,
            age=int(request.form['age']) if request.form.get('age') else None,
            gender=request.form.get('gender') or None,
            crime_type=request.form['crime_type'],
            description=request.form['description'].strip(),
            last_seen_location=request.form.get('last_seen_location', '').strip() or None,
            danger_level=request.form.get('danger_level', 'Medium'),
            reward_info=request.form.get('reward_info', '').strip() or None,
            posted_by_id=current_user.id
        )
        f = request.files.get('photo')
        if f and f.filename and allowed_file(f.filename):
            fn = secure_filename(f.filename)
            unique_fn = str(uuid.uuid4()) + '_' + fn
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_fn))
            wp.photo = unique_fn
        db.session.add(wp)
        db.session.flush()
        public_alert = 'public_alert' in request.form or wp.danger_level == 'Extreme'
        if public_alert:
            broadcast_wanted_alert(wp, f'🚨 PUBLIC ALERT: {wp.full_name} is wanted for {wp.crime_type} and considered a danger to the public. If seen, do not approach — contact police immediately.')
        db.session.commit()
        flash('Wanted announcement published.' + (' Public alert broadcast to all users.' if public_alert else ''), 'success')
        return redirect(url_for('wanted_detail', wid=wp.id))
    return render_template('wanted_form.html')

@app.route('/wanted/<int:wid>')
@login_required
def wanted_detail(wid):
    wp = WantedPerson.query.get_or_404(wid)
    return render_template('wanted_detail.html', person=wp)

@app.route('/wanted/<int:wid>/status', methods=['POST'])
@login_required
def wanted_update_status(wid):
    if current_user.role not in ('admin', 'officer'):
        return redirect(url_for('wanted_list'))
    wp = WantedPerson.query.get_or_404(wid)
    new_status = request.form.get('status', wp.status)
    notes = request.form.get('resolution_notes', '').strip()
    wp.status = new_status
    wp.updated_at = datetime.utcnow()
    if new_status in ('Found', 'Arrested', 'Cleared'):
        wp.resolved_at = datetime.utcnow()
        wp.resolved_by_id = current_user.id
        wp.resolution_notes = notes or None
        db.session.commit()
        verb = {'Found': 'has been located and found', 'Arrested': 'has been arrested', 'Cleared': 'has been cleared of suspicion'}.get(new_status, 'has been updated')
        broadcast_wanted_alert(wp, f'✅ UPDATE: {wp.full_name}, previously wanted for {wp.crime_type}, {verb}. Thank you for staying vigilant.')
    else:
        db.session.commit()
    flash('Status updated.', 'success')
    return redirect(url_for('wanted_detail', wid=wid))

# ── Emergency Alerts ──────────────────────────────────────
def notify_officers_of_emergency(alert):
    officers = User.query.filter(User.role.in_(['admin','officer']), User.is_active==True).all()
    type_label = alert.alert_type
    for o in officers:
        n = Notification(
            user_id=o.id,
            message=f'🚨 EMERGENCY ({type_label}) from {alert.user.full_name} — location received. Tap to view on map.',
            is_emergency=True,
            emergency_id=alert.id
        )
        db.session.add(n)
    db.session.commit()

@app.route('/api/emergency/trigger', methods=['POST'])
@login_required
def trigger_emergency():
    data = request.json or {}
    lat = data.get('latitude'); lng = data.get('longitude')
    if lat is None or lng is None:
        return jsonify({'error': 'Location is required'}), 400
    alert = EmergencyAlert(
        user_id=current_user.id,
        alert_type=data.get('alert_type', 'General'),
        latitude=lat, longitude=lng, accuracy=data.get('accuracy'),
        status='Active'
    )
    db.session.add(alert); db.session.flush()
    db.session.add(LocationPing(alert_id=alert.id, latitude=lat, longitude=lng, accuracy=data.get('accuracy')))
    db.session.commit()
    notify_officers_of_emergency(alert)
    return jsonify({'ok': True, 'alert_id': alert.id})

@app.route('/api/emergency/<int:alert_id>/ping', methods=['POST'])
@login_required
def emergency_ping(alert_id):
    alert = EmergencyAlert.query.get_or_404(alert_id)
    if alert.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    if alert.status == 'Resolved':
        return jsonify({'stopped': True})
    data = request.json or {}
    lat = data.get('latitude'); lng = data.get('longitude')
    if lat is None or lng is None:
        return jsonify({'error': 'Location required'}), 400
    alert.latitude = lat; alert.longitude = lng; alert.accuracy = data.get('accuracy')
    alert.updated_at = datetime.utcnow()
    db.session.add(LocationPing(alert_id=alert.id, latitude=lat, longitude=lng, accuracy=data.get('accuracy')))
    db.session.commit()
    return jsonify({'ok': True, 'status': alert.status})

@app.route('/api/emergency/<int:alert_id>/cancel', methods=['POST'])
@login_required
def cancel_emergency(alert_id):
    alert = EmergencyAlert.query.get_or_404(alert_id)
    if alert.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    alert.status = 'Resolved'; alert.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/emergency')
@login_required
def emergency():
    return render_template('emergency.html')

@app.route('/officer/emergencies')
@login_required
def officer_emergencies():
    if current_user.role not in ('admin','officer'): return redirect(url_for('dashboard'))
    active = EmergencyAlert.query.filter(EmergencyAlert.status != 'Resolved').order_by(EmergencyAlert.created_at.desc()).all()
    resolved = EmergencyAlert.query.filter_by(status='Resolved').order_by(EmergencyAlert.resolved_at.desc()).limit(20).all()
    return render_template('officer_emergencies.html', active=active, resolved=resolved)

@app.route('/api/emergencies/active')
@login_required
def api_active_emergencies():
    if current_user.role not in ('admin','officer'): return jsonify([])
    active = EmergencyAlert.query.filter(EmergencyAlert.status != 'Resolved').order_by(EmergencyAlert.created_at.desc()).all()
    return jsonify([{
        'id': a.id, 'user_name': a.user.full_name, 'user_phone': a.user.phone,
        'alert_type': a.alert_type, 'status': a.status,
        'latitude': a.latitude, 'longitude': a.longitude, 'accuracy': a.accuracy,
        'created_at': a.created_at.strftime('%H:%M:%S'),
        'updated_at': a.updated_at.strftime('%H:%M:%S'),
        'acknowledged_by': a.acknowledged_by.full_name if a.acknowledged_by else None
    } for a in active])

@app.route('/api/emergency/<int:alert_id>/detail')
@login_required
def api_emergency_detail(alert_id):
    if current_user.role not in ('admin','officer'): return jsonify({'error':'Forbidden'}), 403
    a = EmergencyAlert.query.get_or_404(alert_id)
    return jsonify({
        'id': a.id, 'user_name': a.user.full_name, 'user_phone': a.user.phone, 'user_email': a.user.email,
        'alert_type': a.alert_type, 'status': a.status,
        'latitude': a.latitude, 'longitude': a.longitude, 'accuracy': a.accuracy,
        'created_at': a.created_at.strftime('%b %d, %Y %H:%M:%S'),
        'acknowledged_by': a.acknowledged_by.full_name if a.acknowledged_by else None,
        'pings': [{'lat': p.latitude, 'lng': p.longitude, 'time': p.created_at.strftime('%H:%M:%S')} for p in a.pings]
    })

@app.route('/officer/emergency/<int:alert_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_emergency(alert_id):
    if current_user.role not in ('admin','officer'): return jsonify({'error':'Forbidden'}), 403
    a = EmergencyAlert.query.get_or_404(alert_id)
    a.status = 'Acknowledged'; a.acknowledged_by_id = current_user.id; a.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/officer/emergency/<int:alert_id>/resolve', methods=['POST'])
@login_required
def resolve_emergency(alert_id):
    if current_user.role not in ('admin','officer'): return jsonify({'error':'Forbidden'}), 403
    a = EmergencyAlert.query.get_or_404(alert_id)
    a.status = 'Resolved'; a.resolved_at = datetime.utcnow(); a.updated_at = datetime.utcnow()
    db.session.commit()
    n = Notification(user_id=a.user_id, message=f'Your emergency alert has been resolved by {current_user.full_name}. Stay safe.')
    db.session.add(n); db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/emergencies/count')
@login_required
def api_emergencies_count():
    if current_user.role not in ('admin','officer'): return jsonify({'count': 0})
    count = EmergencyAlert.query.filter_by(status='Active').count()
    return jsonify({'count': count})

# ── Notifications ────────────────────────────────────────
@app.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit(); return jsonify({'ok': True})

@app.route('/api/notifications')
@login_required
def api_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(20).all()
    return jsonify([{'id':n.id,'message':n.message,'is_read':n.is_read,'created_at':n.created_at.strftime('%b %d, %H:%M'),
                     'is_emergency':n.is_emergency,'emergency_id':n.emergency_id,
                     'is_wanted_alert':n.is_wanted_alert,'wanted_id':n.wanted_id,
                     'is_chat':n.is_chat,'report_id':n.report_id,
                     'case_number':n.report.case_number if n.report_id else None} for n in notifs])

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ── Seed ────────────────────────────────────────────────
def migrate_db():
    from sqlalchemy import text
    with db.engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(notification)"))]
        if 'is_wanted_alert' not in cols:
            conn.execute(text("ALTER TABLE notification ADD COLUMN is_wanted_alert BOOLEAN DEFAULT 0"))
        if 'wanted_id' not in cols:
            conn.execute(text("ALTER TABLE notification ADD COLUMN wanted_id INTEGER"))
        if 'is_chat' not in cols:
            conn.execute(text("ALTER TABLE notification ADD COLUMN is_chat BOOLEAN DEFAULT 0"))
        report_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(crime_report)"))]
        if 'ai_flag_score' not in report_cols:
            conn.execute(text("ALTER TABLE crime_report ADD COLUMN ai_flag_score REAL DEFAULT 0"))
        if 'ai_flagged' not in report_cols:
            conn.execute(text("ALTER TABLE crime_report ADD COLUMN ai_flagged BOOLEAN DEFAULT 0"))
        if 'ai_flag_reasons' not in report_cols:
            conn.execute(text("ALTER TABLE crime_report ADD COLUMN ai_flag_reasons TEXT"))
        conn.commit()

def seed_db():
    with app.app_context():
        db.create_all()
        migrate_db()
        if not User.query.filter_by(email='admin@crms.go.tz').first():
            admin = User(full_name='System Administrator', email='admin@crms.go.tz', phone='+255700000001', role='admin', email_verified=True)
            admin.set_password('Admin@1234'); db.session.add(admin)
        if not User.query.filter_by(email='officer@crms.go.tz').first():
            officer = User(full_name='Officer John Mwangi', email='officer@crms.go.tz', phone='+255700000002', role='officer', email_verified=True)
            officer.set_password('Officer@1234'); db.session.add(officer)
        if not User.query.filter_by(email='citizen@test.com').first():
            citizen = User(full_name='Jane Kamau', email='citizen@test.com', phone='+255700000003', email_verified=True)
            citizen.set_password('Citizen@1234'); db.session.add(citizen)
            db.session.flush()
            sample = CrimeReport(case_number='CR-202401-DEMO1', user_id=citizen.id,
                crime_type='Theft', description='My phone was stolen at the bus station.',
                location='Arusha Bus Terminal', incident_date=datetime(2024,6,10,14,30),
                status='Under Investigation', priority='High')
            db.session.add(sample)
        db.session.commit()

if __name__ == '__main__':
    seed_db()
    app.run(debug=True, port=5001)

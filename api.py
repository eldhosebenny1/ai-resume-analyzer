from fastapi import FastAPI, UploadFile, File, Form, Request, Depends, HTTPException, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session
import json
import hashlib
import os
import httpx
from dotenv import load_dotenv

from resume_parser import extract_resume_text
from ai_analyzer import analyze_resume
from response_parser import extract_json, calculate_ats_score
from payment_verifier import verify_payment_screenshot
from database import get_db
from models import Analysis, User

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

# --- CONFIGURATION ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key-please-change")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ADMIN_SECRET_TOKEN = os.environ.get("ADMIN_SECRET_TOKEN", "change-me-for-security")

missing_vars = []
if not GOOGLE_CLIENT_ID: missing_vars.append("GOOGLE_CLIENT_ID")
if not GOOGLE_CLIENT_SECRET: missing_vars.append("GOOGLE_CLIENT_SECRET")
if not GOOGLE_API_KEY: missing_vars.append("GOOGLE_API_KEY (for Gemini AI)")
if not TELEGRAM_BOT_TOKEN: missing_vars.append("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_CHAT_ID: missing_vars.append("TELEGRAM_CHAT_ID")

if missing_vars:
    print(f"⚠️ WARNING: The following environment variables are missing: {', '.join(missing_vars)}")
    print("👉 Please check your .env file or system environment variables.")

app = FastAPI()

# --- DATABASE INITIALIZATION ---
from database import engine
from models import Base
Base.metadata.create_all(bind=engine)

# Add Proxy Headers Middleware for Render/HTTPS support
try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
except ImportError:
    pass

# Add Session Middleware (Required for OAuth)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="templates")
app.mount("/templates", StaticFiles(directory="templates"), name="templates")

# --- OAUTH SETUP ---
oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# --- UTILS ---
def make_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def get_current_user(request: Request):
    return request.session.get('user')

# --- AUTH ROUTES ---
@app.get("/login")
async def login(request: Request):
    # Redirect to Google Login
    redirect_uri = request.url_for('auth_callback')
    
    # Force HTTPS for the redirect URI if running on Render/Production
    if "render.com" in str(request.base_url) or request.headers.get("x-forwarded-proto") == "https":
        redirect_uri = str(redirect_uri).replace("http://", "https://")
    
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
             # Look inside 'id_token' if 'userinfo' is empty (depends on authlib version)
             user_info = await oauth.google.parse_id_token(request, token)
        
        # Save or Update User in DB
        user = db.query(User).filter(User.google_id == user_info['sub']).first()
        if not user:
            user = User(
                google_id=user_info['sub'],
                email=user_info['email'],
                name=user_info.get('name'),
                picture=user_info.get('picture')
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        # Store user in session
        request.session['user'] = {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "picture": user.picture
        }
        
        return RedirectResponse(url='/')
    except Exception as e:
        print(f"Auth Error: {e}")
        return RedirectResponse(url='/?error=AuthFailed')

@app.get("/logout")
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url='/')

# --- MAIN ROUTES ---
@app.get("/")
def home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.post("/analyze")
async def analyze(
    request: Request,
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    db: Session = Depends(get_db)
):
    user_session = get_current_user(request)
    
    if not user_session:
         return templates.TemplateResponse("index.html", {
             "request": request,
             "user": None,
             "error": "Please sign in with Google to evaluate your resume."
         })
    
    contents = await resume.read()
    with open("temp_resume.pdf", "wb") as f:
        f.write(contents)

    resume_text = extract_resume_text("temp_resume.pdf")

    resume_hash = make_hash(resume_text)
    job_hash = make_hash(job_description)

    # 🔍 Check if analysis already exists
    analysis_row = (
        db.query(Analysis)
        .filter(
            Analysis.resume_hash == resume_hash,
            Analysis.job_hash == job_hash
        )
        .first()
    )

    if analysis_row:
        analysis_raw = json.loads(analysis_row.analysis_json)
        is_paid = analysis_row.is_paid
        analysis_id = analysis_row.id
        
        # Link to user if logged in and not already linked
        if user_session and not analysis_row.user_id:
            analysis_row.user_id = user_session['id']
            db.commit()
            
    else:
        raw_response = analyze_resume(resume_text, job_description)
        analysis_raw = extract_json(raw_response)
        
        # 🛡️ HANDLE INVALID RESUMES
        if "error" in analysis_raw:
             return templates.TemplateResponse("index.html", {
                 "request": request,
                 "user": user_session,
                 "error": analysis_raw["error"]
             })

        analysis_raw["ats_score"] = calculate_ats_score(analysis_raw)

        analysis_id = analysis_raw.get("id") or None

        analysis_row = Analysis(
            resume_hash=resume_hash,
            job_hash=job_hash,
            analysis_json=json.dumps(analysis_raw),
            is_paid=False,
            user_id=user_session['id'] if user_session else None
        )
        db.add(analysis_row)
        db.commit()
        db.refresh(analysis_row)

        analysis_id = analysis_row.id
        is_paid = False

    # 🔓 GLOBAL UNLOCK FOR USER + RESUME (Regardless of JD)
    if user_session and not is_paid:
        # Check if user has paid for this exact resume hash in ANY other analysis
        paid_resume_exists = db.query(Analysis).filter(
            Analysis.user_id == user_session['id'],
            Analysis.resume_hash == resume_hash,
            Analysis.is_paid == True
        ).first()

        if paid_resume_exists:
            is_paid = True
            # Update current row to be paid too for future speed
            analysis_row.is_paid = True
            db.commit()

    analysis = adapt_for_ui(analysis_raw)
    analysis = ensure_min_items(analysis)
    
    # 🔒 Apply Paywall if not paid
    analysis = apply_paywall(analysis, is_paid)

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "user": user_session,
            "analysis": analysis,
            "analysis_id": analysis_id,
            "is_paid": is_paid,
            "payment_status": analysis_row.payment_status if analysis_row else "unpaid"
        }
    )

def apply_paywall(analysis: dict, is_paid: bool):
    """Unified function to hide premium data if not paid."""
    if not is_paid:
        analysis["grammar_fixes"] = (analysis.get("grammar_fixes") or [])[:2]
        analysis["missing_skills"] = (analysis.get("missing_skills") or [])[:2]
        
        # Hide everything else
        analysis["improved_bullets"] = []
        analysis["critical_issues"] = []
        analysis["recruiter_quick_scan"] = None
        analysis["formatting_suggestions"] = []
        analysis["premium_tips"] = []
    return analysis

@app.post("/unlock")
async def unlock(
    request: Request,
    analysis_id: str = Form(...),
    screenshot: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user_session = get_current_user(request)
    analysis_row = db.query(Analysis).filter(Analysis.id == analysis_id).first()

    if not analysis_row:
        return {"error": "Invalid analysis ID"}

    # --- PROCESS SCREENSHOT ---
    try:
        content = await screenshot.read()
        if not screenshot.content_type.startswith("image/"):
             raise Exception("Please upload an image file (PNG/JPG/etc.)")
        
        # --- AUTOMATIC VERIFICATION ---
        expected_receiver = "bennyeldho2@okicici or bennyeldho2-1@oksbi"
        expected_amount = 40.0
        
        is_valid, v_message, v_details = verify_payment_screenshot(content, expected_receiver, expected_amount)
        print(f"Auto-Verification Result: {is_valid} - {v_message}")

        # Detect app base URL for the approval link
        base_url = str(request.base_url)
        if "render.com" in base_url or request.headers.get("x-forwarded-proto") == "https":
            base_url = base_url.replace("http://", "https://")
            
        approval_url = f"{base_url.rstrip('/')}/approve-payment/{analysis_id}/{ADMIN_SECRET_TOKEN}"
        
        status_tag = "✅ AUTO-VERIFIED" if is_valid else "⚠️ MANUAL REVIEW"
        
        message = (
            f"{status_tag}\n"
            f"💰 *New Payment Submission*\n\n"
            f"👤 User: {user_session['name'] if user_session else 'Guest'}\n"
            f"📧 Email: {user_session['email'] if user_session else 'N/A'}\n"
            f"🆔 Analysis ID: `{analysis_id}`\n"
            f"📝 Detail: {v_message}\n\n"
            f"🔍 *Extracted Details:*\n"
            f"💵 Amount: {v_details.get('amount') if v_details else 'N/A'}\n"
            f"📅 Date: {v_details.get('transaction_date') if v_details else 'N/A'}\n"
            f"🕒 Time: {v_details.get('transaction_time') if v_details else 'N/A'}\n"
            f"🆔 Txn ID: `{v_details.get('transaction_id') if v_details else 'N/A'}`\n\n"
            f"🔗 [VIEW REPORT]({base_url.rstrip('/')}/result-page/{analysis_id})\n"
            f"🔗 [MANUAL APPROVE]({approval_url})"
        )

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": message,
                    "parse_mode": "Markdown"
                },
                files={"photo": (screenshot.filename, content, screenshot.content_type)}
            )
            
        if is_valid:
            analysis_row.is_paid = True
            analysis_row.payment_status = "paid"
            db.commit()
            return RedirectResponse(url=f"/result-page/{analysis_id}", status_code=303)
        else:
            # Auto-verification failed.
            # We do NOT set it to pending in DB so the user can try again immediately.
            # But we still send it to Telegram for manual review as a backup.
            db.commit() 
            
            analysis_raw = json.loads(analysis_row.analysis_json)
            analysis = adapt_for_ui(analysis_raw)
            analysis = ensure_min_items(analysis)
            analysis = apply_paywall(analysis, False)
            
            error_msg = f"Auto-Verification Failed: {v_message}"
            
            return templates.TemplateResponse(
                "result.html",
                {
                    "request": request,
                    "user": user_session,
                    "analysis": analysis,
                    "analysis_id": analysis_id,
                    "is_paid": False,
                    "payment_status": analysis_row.payment_status, # Remains 'unpaid'
                    "error": error_msg
                }
            )
    except Exception as e:
        analysis_raw = json.loads(analysis_row.analysis_json)
        analysis = adapt_for_ui(analysis_raw)
        analysis = ensure_min_items(analysis)
        analysis = apply_paywall(analysis, False) # Force paywall on error
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "user": user_session,
                "analysis": analysis,
                "analysis_id": analysis_id,
                "is_paid": False,
                "payment_status": analysis_row.payment_status if analysis_row else "unpaid",
                "error": f"Error: {str(e)}"
            }
        )

    return RedirectResponse(url=f"/result-page/{analysis_id}", status_code=303)

@app.get("/result-page/{analysis_id}")
async def view_result_by_id(request: Request, analysis_id: str, db: Session = Depends(get_db)):
    user_session = get_current_user(request)
    analysis_row = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    
    if not analysis_row:
        return RedirectResponse(url="/")
        
    analysis_raw = json.loads(analysis_row.analysis_json)
    analysis = adapt_for_ui(analysis_raw)
    analysis = ensure_min_items(analysis)
    
    # 🔒 Apply Paywall
    is_paid = analysis_row.is_paid
    analysis = apply_paywall(analysis, is_paid)

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "user": user_session,
            "analysis": analysis,
            "analysis_id": analysis_id,
            "is_paid": is_paid,
            "payment_status": analysis_row.payment_status
        }
    )

@app.get("/approve-payment/{analysis_id}/{token}")
async def approve_payment(analysis_id: str, token: str, db: Session = Depends(get_db)):
    if token != ADMIN_SECRET_TOKEN:
        return Response(content="Unauthorized", status_code=401)
        
    analysis_row = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis_row:
        return Response(content="Not Found", status_code=404)
        
    analysis_row.is_paid = True
    analysis_row.payment_status = "paid"
    db.commit()
    
    return Response(content="✅ Payment approved! User can now refresh their page to see full results.", media_type="text/plain")

def adapt_for_ui(raw: dict):
    return {
        "ats_score": raw.get("ats_score"),
        "overall_assessment": raw.get("overall_assessment", {}),
        "grammar_fixes": raw.get("grammar_and_language_fixes", []),
        "missing_skills": raw.get("missing_skills", []),
        "improved_bullets": [
            f"{b['original']} → {b['improved']}"
            for b in raw.get("bullet_improvements", [])
        ],
        "critical_issues": raw.get("critical_issues", []),
        "recruiter_quick_scan": raw.get("recruiter_quick_scan_comment"),
        "formatting_suggestions": raw.get("formatting_and_structure_tips", []),
        "premium_tips": raw.get("premium_standout_tips", [])
    }

# -------------------------------
# SAFETY FALLBACKS
# -------------------------------

def ensure_min_items(data: dict):
    if not data.get("formatting_suggestions"):
        data["formatting_suggestions"] = [
            "Ensure consistent bullet formatting across sections",
            "Use standard ATS-friendly headings (Skills, Experience, Projects)",
            "Place Skills section immediately after Summary",
            "Limit resume to 1–2 pages with consistent spacing",
            "Avoid symbols, icons, or excessive capitalization"
        ]

    if not data.get("missing_skills"):
        data["missing_skills"] = [
            "REST API fundamentals",
            "Basic cloud deployment concepts",
            "Data structures and algorithms",
            "Version control best practices",
            "Problem-solving in production systems"
        ]

    return data
# -------------------------------
# CORS (Keep existing)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -------------------------------
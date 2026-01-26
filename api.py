from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from resume_parser import extract_resume_text
from ai_analyzer import analyze_resume
from response_parser import extract_json, calculate_ats_score

from sqlalchemy.orm import Session
from fastapi import Depends
import json
import hashlib

from database import get_db
from models import Analysis






def make_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/templates", StaticFiles(directory="templates"), name="templates")


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/analyze")
async def analyze(
    request: Request,
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    db: Session = Depends(get_db)
):
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
    else:
        raw_response = analyze_resume(resume_text, job_description)
        analysis_raw = extract_json(raw_response)
        analysis_raw["ats_score"] = calculate_ats_score(analysis_raw)

        analysis_id = analysis_raw.get("id") or None

        analysis_row = Analysis(
            resume_hash=resume_hash,
            job_hash=job_hash,
            analysis_json=json.dumps(analysis_raw),
            is_paid=False
        )
        db.add(analysis_row)
        db.commit()
        db.refresh(analysis_row)

        analysis_id = analysis_row.id
        is_paid = False

    analysis = adapt_for_ui(analysis_raw)
    analysis = ensure_min_items(analysis)

    # 🔒 FREE vs PAID LOGIC
    if not is_paid:
        analysis["grammar_fixes"] = analysis["grammar_fixes"][:2]
        analysis["missing_skills"] = analysis["missing_skills"][:2]

        analysis["improved_bullets"] = []
        analysis["critical_issues"] = []
        analysis["recruiter_quick_scan"] = None
        analysis["formatting_suggestions"] = []
        analysis["premium_tips"] = []

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "analysis": analysis,
            "analysis_id": analysis_id,
            "is_paid": is_paid
        }
    )

from fastapi import Form

@app.post("/unlock")
@app.post("/unlock/")
def unlock(
    request: Request,
    analysis_id: str = Form(...),
    transaction_id: str = Form(...),
    db: Session = Depends(get_db)
):
    analysis_row = db.query(Analysis).filter(Analysis.id == analysis_id).first()

    if not analysis_row:
        return {"error": "Invalid analysis ID"}

    # 🔒 Soft validation
    if len(transaction_id.strip()) < 8:
        return {"error": "Invalid transaction ID"}

    analysis_row.is_paid = True
    analysis_row.payment_reference = transaction_id.strip()
    db.commit()

    analysis_raw = json.loads(analysis_row.analysis_json)
    analysis = adapt_for_ui(analysis_raw)
    analysis = ensure_min_items(analysis)

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "analysis": analysis,
            "analysis_id": analysis_id,
            "is_paid": True
        }
    )



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
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -------------------------------
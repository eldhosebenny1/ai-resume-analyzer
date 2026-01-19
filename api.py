from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.templating import Jinja2Templates
from resume_parser import extract_resume_text
from ai_analyzer import analyze_resume
from response_parser import extract_json
from response_parser import calculate_ats_score

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/analyze")
async def analyze(
    request: Request,
    resume: UploadFile = File(...),
    job_description: str = Form(...)
):
    contents = await resume.read()
    with open("temp_resume.pdf", "wb") as f:
        f.write(contents)

    resume_text = extract_resume_text("temp_resume.pdf")
    raw_response = analyze_resume(resume_text, job_description)
    analysis = extract_json(raw_response)
    analysis["ats_score"] = calculate_ats_score(analysis)
    analysis = adapt_for_ui(analysis)
    analysis = ensure_min_items(analysis)
    return templates.TemplateResponse(
        "result.html",
        {"request": request, "analysis": analysis}
    )
def adapt_for_ui(raw: dict) -> dict:
    return {
        "ats_score": raw.get("ats_score"),
        "grammar_fixes": raw.get("grammar_and_language_fixes", []),
        "formatting_suggestions": raw.get("formatting_and_structure_tips", []),
        "missing_skills": raw.get("keyword_analysis", {}).get("missing_critical", []),
        "improved_bullets": [
            f"{b['original']} → {b['improved']}"
            for b in raw.get("bullet_improvements", [])
        ],
        "final_tips": raw.get("premium_standout_tips", [])
    }
def ensure_min_items(data: dict):
    if not data.get("formatting_suggestions"):
        data["formatting_suggestions"] = [
            "Ensure consistent bullet point formatting across all sections",
            "Use standard section headings such as Skills, Experience, Projects",
            "Place Skills section immediately after Summary for ATS parsing",
            "Limit resume length to 1–2 pages with consistent spacing",
            "Avoid excessive capitalization or symbols in headings"
        ]

    if not data.get("missing_skills"):
        data["missing_skills"] = [
            "REST API fundamentals",
            "Basic cloud deployment concepts",
            "Data structures and algorithms",
            "Version control best practices",
            "Problem-solving in production environments"
        ]

    return data



from resume_parser import extract_resume_text
from ai_analyzer import analyze_resume
from response_parser import extract_json

if __name__ == "__main__":
    resume_text = extract_resume_text("resume_eldhose.pdf")

    job_description = """
    Looking for a Python developer with experience in FastAPI,
    REST APIs, SQL, and basic cloud deployment.
    """

    raw_response = analyze_resume(resume_text, job_description)

    try:
        analysis = extract_json(raw_response)
        print("\n===== CLEAN AI ANALYSIS =====\n")
        print(analysis)
    except ValueError as e:
        print("\n❌ Failed to parse AI response")
        print(str(e))
        print("\nRAW RESPONSE:")
        print(raw_response)

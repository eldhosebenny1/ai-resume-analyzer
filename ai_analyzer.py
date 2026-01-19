from google import genai

# Uses GOOGLE_API_KEY from environment variable
client = genai.Client()

def analyze_resume(resume_text: str, job_description: str) -> str:
    """
    Premium ATS + recruiter-grade resume analysis.
    Returns ONLY valid JSON. No markdown. No explanations.
    """

    prompt = f"""
You are a senior ATS resume evaluator and technical recruiter
working with 2025–2026 hiring standards.

Resume:
{resume_text}

Job Description:
{job_description}

STRICT RULES (MUST FOLLOW):
- Do NOT add fake skills, tools, metrics, achievements, or experience
- Do NOT invent dates or responsibilities
- Do NOT exaggerate; preserve candidate truth
- All suggestions must be ATS-safe (plain text, no tables, no graphics)
- Use concise, modern, professional language
- This is a paid analysis — be direct and honest

OUTPUT RULES:
- Return ONLY valid JSON
- No markdown, no comments, no explanations
- All required fields must exist
- Do NOT return fewer items than the minimum counts below

JSON STRUCTURE (exact keys required):
{{
  "keyword_match_score": number,
  "formatting_score": number,
  "language_score": number,

  "overall_assessment": {{
    "match_tier": "Poor|Fair|Average|Good|Strong|Excellent|Elite",
    "one_line_summary": "short honest assessment of resume strength"
  }},

  "grammar_and_language_fixes": [
    "Original → Improved"
  ],

  "missing_skills": [
    "skill or keyword"
  ],

  "bullet_improvements": [
    {{
      "original": "exact original bullet text",
      "improved": "optimized version"
    }}
  ],

  "critical_issues": [
    {{
      "severity": "Critical|High|Medium|Low",
      "issue": "short issue title",
      "fix_suggestion": "concise fix"
    }}
  ],

  "premium_standout_tips": [
    "advanced resume / personal branding improvement"
  ],

  "recruiter_quick_scan_comment": "what a senior recruiter thinks in 7 seconds"
}}

MANDATORY MINIMUM COUNTS (VERY IMPORTANT):
- grammar_and_language_fixes: MIN 6, MAX 10
- missing_skills: MIN 5, MAX 8
- bullet_improvements: MIN 5, MAX 8
- critical_issues: MIN 4, MAX 6
- premium_standout_tips: MIN 5, MAX 7

IF CONTENT IS LIMITED:
- Rewrite weak lines
- Split compound issues into multiple items
- Use safe inferences based on resume wording
- NEVER return fewer than the minimum counts

Be strict, practical, and premium-quality.

ABSOLUTE REQUIREMENTS (NO EXCEPTIONS):

- formatting_and_structure_tips MUST contain at least 5 items.
  If formatting is already good:
  - Suggest micro-improvements
  - Suggest reordering sections
  - Suggest consistency improvements
  - Suggest ATS optimization tweaks

- missing_skills MUST contain at least 5 items.
  If few skills are missing:
  - Include weakly implied skills
  - Include commonly expected adjacent skills
  - Include role-aligned tooling or concepts
  - NEVER return an empty array

- DO NOT return empty arrays for ANY section.
- If uncertain, provide safe, conservative suggestions.
- ALWAYS meet the MINIMUM item counts specified above.
"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config={
            "temperature": 0.0
        }
    )

    return response.text

from google import genai

client = genai.Client()

def analyze_resume(resume_text: str, job_description: str) -> str:
    """
    Premium ATS + recruiter-grade resume analysis.
    Returns ONLY valid JSON.
    """

    prompt = f"""
You are a senior ATS resume evaluator and technical recruiter (2025–2026 standards).

Resume:
{resume_text}

Job Description:
{job_description}

STRICT RULES:
- Do NOT add fake skills, tools, metrics, achievements, or experience
- Do NOT modify dates or invent responsibilities
- Keep all suggestions ATS-safe (no tables, no graphics)
- Use concise, professional, modern language
- Be honest and critical — this is a paid analysis

Return ONLY valid JSON. No explanations. No markdown.

JSON structure:
{{
  "keyword_match_score": number,
  "formatting_score": number,
  "language_score": number,

  "overall_assessment": {{
    "match_tier": "Poor|Fair|Average|Good|Strong|Excellent|Elite",
    "one_line_summary": "short honest assessment"
  }},

  "keyword_analysis": {{
    "found_essential": ["..."],
    "missing_critical": ["..."],
    "nice_to_have_missing": ["..."],
    "estimated_ats_parse_score": number
  }},

  "critical_issues": [
    {{
      "severity": "Critical|High|Medium|Low",
      "issue": "short title",
      "where": "resume section",
      "why_it_hurts": "brief reason",
      "fix_suggestion": "concise fix"
    }}
  ],

  "grammar_and_language_fixes": [
    "Original → Improved"
  ],

  "bullet_improvements": [
    {{
      "original": "exact original bullet",
      "improved": "optimized bullet",
      "change_type": "Verb|Impact|Keyword|Clarity|Conciseness",
      "impact_potential": "Low|Medium|High|Very High"
    }}
  ],

  "formatting_and_structure_tips": [
    "actionable ATS-safe suggestion"
  ],

  "skills_recommendations": {{
    "current_skills_detected": ["..."],
    "strongly_recommended_to_add": ["only if safe"],
    "can_be_added_if_true": ["..."]
  }},

  "premium_standout_tips": [
    "advanced differentiation advice"
  ],

  "recruiter_quick_scan_comment": "7-second recruiter impression"
}}
"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config={
            "temperature": 0.0
        }
    )

    return response.text

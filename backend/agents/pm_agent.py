import os
import json
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# Load .env from backend folder
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

def get_gemini_model():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(f"GOOGLE_API_KEY not found or default in {env_path}")
    genai.configure(api_key=api_key)
    # Try gemini-flash-latest, gemini-2.0-flash-lite, gemini-pro-latest
    for model_name in ["gemini-flash-latest", "gemini-2.0-flash-lite", "gemini-pro-latest", "gemini-2.0-flash"]:
        try:
            return genai.GenerativeModel(model_name)
        except Exception:
            continue
    return genai.GenerativeModel("gemini-flash-latest")


def generate_pm_output(user_prompt: str):
    prompt = f"""
You are a Senior Project Manager AI.

Convert the user idea into structured JSON.

STRICT RULES:
- Output ONLY valid JSON
- No explanation
- No markdown
- Follow schema exactly

SCHEMA:
{{
  "project_name": "",
  "description": "",
  "features": [],
  "tech_stack": {{
    "frontend": "React",
    "backend": "FastAPI",
    "database": "SQLite"
  }},
  "database_entities": [
    {{
      "name": "",
      "fields": [
        {{
          "name": "",
          "type": ""
        }}
      ]
    }}
  ]
}}

USER IDEA:
{user_prompt}
"""

    model = get_gemini_model()
    response = model.generate_content(prompt)
    return response.text


if __name__ == "__main__":
    result = generate_pm_output("Build a task management app")
    os.makedirs("outputs", exist_ok=True)
    with open("outputs/pm_output.json", "w", encoding="utf-8") as f:
        json.dump(json.loads(result), f, indent=2)
    print(result)
    
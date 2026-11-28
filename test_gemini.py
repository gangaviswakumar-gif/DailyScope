
import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env")

MODEL_NAME = "gemini-3.5-flash-lite"

client = genai.Client(api_key=api_key)

# Example article for testing only
article = """
Headline: Kerala launches a fictional digital learning initiative.

Description:
The Kerala government has announced a fictional initiative
to provide digital learning facilities in government schools.
The proposed programme includes computer laboratories
and internet access.
"""

prompt = f"""
You are a professional news editor working for DailyScope.

Create a news report using ONLY the information provided below.

Do not invent facts, statistics, dates, names or outcomes.
If information is unavailable, clearly mention that.

ARTICLE:
{article}

Generate:
1. A clear headline.
2. A factual summary.
3. Relevant background based only on the supplied information.
4. The potential impact, clearly distinguishing expected
   impact from confirmed outcomes.
"""

# Define the expected JSON structure
response_schema = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "background": {"type": "string"},
        "impact": {"type": "string"}
    },
    "required": [
        "title",
        "summary",
        "background",
        "impact"
    ],
    "additionalProperties": False
}

response = client.interactions.create(
    model=MODEL_NAME,
    input=prompt,
    response_format={
        "type": "text",
        "mime_type": "application/json",
        "schema": response_schema
    }
)

# Convert JSON response into a Python dictionary
report = json.loads(response.output_text)

print("\n========== DAILY SCOPE NEWS REPORT ==========\n")

for section, content in report.items():
    print(f"\n{section.upper()}:")
    print(content)

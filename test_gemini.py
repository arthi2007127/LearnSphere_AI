import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise SystemExit("Gemini API key not found in .env")

client = genai.Client(api_key=api_key)

try:
    print("Testing Gemini text generation...\n")

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=(
            "Create one easy aptitude question with four options. "
            "Give the correct answer and a short explanation."
        ),
    )

    print("SUCCESS! AI generation is working.")
    print(response.text)

except Exception as error:
    print("AI request failed.")
    print("Error type:", type(error).__name__)
    print("Error details:", str(error))
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise SystemExit(
        "API key not found. Check your .env file."
    )

client = OpenAI(api_key=api_key)

try:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input="Create one easy quantitative aptitude question with four options and its correct answer."
    )

    print("\nAI response:\n")
    print(response.output_text)

except Exception as error:
    print("API request failed.")
    print("Error type:", type(error).__name__)
    print("Check your API key, API access, and billing settings.")
import httpx
import os
import json
import time
from google import genai
from google.genai import errors
from dotenv import load_dotenv

load_dotenv()


def generate_coding_challenge(
    language="Python",
    difficulty="Easy",
    topic="Basics"
):
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.8-flash"
    )

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is missing from your .env file."
        )

    client = genai.Client(api_key=api_key)

    prompt = f"""
Create one original programming challenge.

Language: {language}
Difficulty: {difficulty}
Topic: {topic}

Return ONLY valid JSON. Do not use Markdown code fences.

Use exactly these fields:
{{
  "title": "Challenge title",
  "description": "Explain the problem clearly",
  "input_format": "Describe the input",
  "output_format": "Describe the output",
  "examples": [
    {{
      "input": "sample input",
      "output": "sample output",
      "explanation": "Explain the example"
    }}
  ],
  "constraints": ["constraint 1"],
  "starter_code": "Starter code as a string",
  "hints": ["Hint 1", "Hint 2"],
  "solution": "Complete reference solution as a string",
  "explanation": "Explain the solution step by step"
}}

Make the challenge suitable for the selected difficulty.
Ensure the examples and solution are correct.
"""

    
    response = None

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )

            if response is not None and response.text:
                break

            if attempt == 2:
                raise ValueError(
                    "The AI returned an empty response."
                )

        except (
            errors.ServerError,
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
        ):
            if attempt == 2:
                raise

        time.sleep(2 * (attempt + 1))

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )
            break

        except errors.ServerError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

    if response is None or not response.text:
        raise ValueError("The AI returned an empty response.")

    text = response.text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "", 1)
        text = text.replace("```", "").strip()

    challenge = json.loads(text)

    required_fields = [
        "title",
        "description",
        "input_format",
        "output_format",
        "examples",
        "constraints",
        "starter_code",
        "hints",
        "solution",
        "explanation",
    ]

    for field in required_fields:
        if field not in challenge:
            raise ValueError(
                f"The AI response is missing: {field}"
            )

    return challenge

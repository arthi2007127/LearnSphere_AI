import json
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key) if api_key else None

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def generate_questions(topic, difficulty, count=5):
    if client is None:
        raise RuntimeError("Gemini API key is not configured.")

    count = max(1, min(int(count), 10))

    prompt = f"""
    You are an expert placement-exam question setter.

    Generate exactly {count} multiple-choice questions.

    Topic: {topic}
    Difficulty: {difficulty}

    Requirements:
    - Each question must have four options.
    - Exactly one option must be correct.
    - Include a short explanation.
    - Questions should be clear and educational.
    - Avoid repeating questions within this response.
    - Do not include markdown code fences.

    Return valid JSON using this structure:

    {{
      "questions": [
        {{
          "question": "Question text",
          "options": [
            "Option A",
            "Option B",
            "Option C",
            "Option D"
          ],
          "answer": 0,
          "explanation": "Explanation"
        }}
      ]
    }}

    The answer must be an integer from 0 to 3.
    """

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "response_mime_type": "application/json"
        },
    )

    data = json.loads(response.text)
    questions = data.get("questions", [])

    if len(questions) != count:
        raise ValueError("AI returned an unexpected number of questions.")

    for question in questions:
        if not isinstance(question.get("question"), str):
            raise ValueError("Invalid question text.")

        options = question.get("options")

        if not isinstance(options, list) or len(options) != 4:
            raise ValueError("Each question must have four options.")

        answer = question.get("answer")

        if isinstance(answer, bool) or not isinstance(answer, int):
            raise ValueError("Answer must be an integer.")

        if answer not in range(4):
            raise ValueError("Answer must be between 0 and 3.")

        if not all(isinstance(option, str) and option.strip()
                   for option in options):
            raise ValueError("Question options cannot be empty.")

        if not isinstance(question.get("explanation"), str):
            raise ValueError("Question explanation is missing.")

    return questions

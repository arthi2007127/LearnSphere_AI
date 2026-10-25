
import json
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

# Use the same model configured in your working AI service.
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def get_english_feedback(message, mode="conversation", level="adaptive"):
    if client is None:
        raise RuntimeError("Gemini API key is not configured.")
    allowed_levels = {
        "adaptive", "beginner", "intermediate", "advanced"
    }

    if level not in allowed_levels:
        level = "adaptive"
    
    allowed_modes = {
        "conversation",
        "grammar",
        "interview",
        "vocabulary",
    }

    if mode not in allowed_modes:
        mode = "conversation"

    message = message.strip()

    if not message:
        raise ValueError("Please enter a message.")

    if len(message) > 3000:
        raise ValueError("Please keep your answer under 3000 characters.")

    prompt = f"""
    Student English level: {level}

If the level is adaptive, estimate the student's level from their
message and adapt your explanation to it. Do not claim that one
short message determines their overall proficiency accurately.

Use simple explanations for beginners and more advanced feedback
for intermediate and advanced students.

You are LearnSphere AI English Coach.

Practice mode: {mode}

Student's English text:
{message}

Help the student learn English in a friendly and encouraging way.

For grammar mode:
- Show the corrected sentence.
- Explain the grammar mistake simply.
- Give one more example.

For conversation mode:
- Reply naturally to the student's message.
- Suggest a more natural English sentence when useful.
- Ask one simple follow-up question.

For interview mode:
- Improve the student's answer professionally.
- Explain important improvements.
- Give one interview tip.

For vocabulary mode:
- Identify useful vocabulary.
- Explain meanings simply.
- Give example sentences.

Return ONLY valid JSON with this structure:
{{
  "feedback": "Your complete helpful feedback as plain text."
}}

Do not judge the student's intelligence or personality.
Be respectful and beginner-friendly.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    data = json.loads(response.text)
    feedback = data.get("feedback")

    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("The AI returned invalid feedback.")

    return feedback

def get_pronunciation_practice_feedback(sentence, level="adaptive"):
    """Generate word-by-word English learning feedback."""

    if client is None:
        raise RuntimeError("Gemini API key is not configured.")

    if not isinstance(sentence, str) or not sentence.strip():
        raise ValueError("Please enter or speak a sentence first.")

    sentence = sentence.strip()

    if len(sentence) > 1000:
        raise ValueError("Please keep your sentence under 1000 characters.")

    allowed_levels = {
        "adaptive", "beginner", "intermediate", "advanced"
    }

    if level not in allowed_levels:
        level = "adaptive"

    prompt = f"""
You are LearnSphere AI English Coach.

Student English level: {level}
Student sentence: {sentence}

Analyse the sentence for English learning.

Return ONLY valid JSON with this exact structure:
{{
  "corrected_sentence": "The grammatically corrected sentence",
  "words": [
    {{
      "word": "word from the sentence",
      "meaning": "Simple English meaning",
      "pronunciation_tip": "A useful tip for practising this word",
      "example": "A short example sentence"
    }}
  ],
  "grammar_feedback": "Explain any important grammar corrections simply",
  "overall_tip": "One practical suggestion for improvement"
}}

Requirements:
- Explain important words individually.
- Keep the feedback suitable for the selected student level.
- Do not invent errors if the sentence is already correct.
- Use pronunciation tips, not unsupported claims about how the student
  actually pronounced a word.
- Do not claim to have heard or measured pronunciation accuracy.
- Be encouraging and concise.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    try:
        data = json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("The AI returned an invalid response. Please try again.")

    if not isinstance(data, dict) or not isinstance(data.get("words"), list):
        raise ValueError("The AI returned incomplete feedback. Please try again.")

    return data

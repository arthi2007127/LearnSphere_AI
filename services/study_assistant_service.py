import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

_api_key = os.getenv("GEMINI_API_KEY")
_client = genai.Client(api_key=_api_key) if _api_key else None
_model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

_MODE_INSTRUCTIONS = {
    "tutor": "Teach the concept in plain language, use a relevant example or analogy, then finish with one short check-for-understanding question.",
    "quiz": "Act as a quiz coach. Ask one question at a time and do not reveal the answer until the learner attempts it. If the learner has answered the previous question, explain the answer briefly and ask the next one.",
    "flashcards": "Create five concise flashcards. Format each as 'Front: ...' followed by 'Back: ...'. Focus on recall, not trivia, and keep each answer short.",
    "plan": "Create a realistic study plan using the learner's available time and goal. Break it into timed blocks with short breaks, active recall, and a final review. If time or deadline is missing, state a reasonable assumption.",
    "summary": "Summarize the supplied notes into key ideas, important terms, and three quick self-test questions. Keep the summary faithful to the notes and flag anything ambiguous.",
    "career": "Act as a supportive placement preparation coach. Tailor advice to the learner's target role, timeline, and chosen focus. Give a short actionable next step. For mock interview practice, ask one realistic question at a time, wait for the learner's answer, then give specific feedback on structure, evidence, and clarity. Be honest and do not promise job outcomes.",
}


def generate_study_reply(mode, subject, message, history=None):
    """Generate a focused study response for one of the supported modes."""
    if _client is None:
        raise RuntimeError("Study Assistant needs GEMINI_API_KEY configured in the app environment.")
    if mode not in _MODE_INSTRUCTIONS:
        raise ValueError("Choose a valid study mode.")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Enter a topic, question, or notes to get started.")
    if len(message) > 6000:
        raise ValueError("Please keep your message under 6,000 characters.")

    conversation = []
    for item in (history or [])[-10:]:
        role = "Learner" if item.get("role") == "user" else "Study Assistant"
        content = item.get("content", "")
        if isinstance(content, str):
            conversation.append(f"{role}: {content[:3000]}")
    context = "\n".join(conversation) or "No earlier messages."

    prompt = f"""
You are LearnSphere AI, a patient study assistant. Help the learner understand
and remember material. Be accurate, encouraging, and clear. Do not invent
facts; say when you are unsure. Use Markdown headings and lists when helpful.

Study mode: {mode}
Subject or course: {subject[:120] or 'General study'}
Instructions for this mode: {_MODE_INSTRUCTIONS[mode]}

Recent conversation:
{context}

Learner's latest message:
{message.strip()}

Answer the latest message using the selected mode. Keep the response useful
and focused. Do not claim to have checked external sources.
"""
    result = _client.models.generate_content(
        model=_model_name,
        contents=prompt,
    )
    response = getattr(result, "text", None)
    if not isinstance(response, str) or not response.strip():
        raise ValueError("The Study Assistant returned an empty response. Please try again.")
    return response.strip()

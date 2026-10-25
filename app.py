from pathlib import Path
from services.english_coach_service import (
    get_english_feedback,
    get_pronunciation_practice_feedback,
)
from dotenv import load_dotenv
load_dotenv()
from email.message import EmailMessage
import smtplib
import ssl
from services.code_lab_service import generate_coding_challenge
from services.ai_question_service import generate_questions
from services.study_assistant_service import generate_study_reply
from flask import (
    Flask, request, jsonify, render_template, current_app,
    redirect, url_for, flash
)
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user,
)

from config import Config
from models import (
    db, User, QuizAttempt, InterviewChallengeCompletion,
    InterviewPracticeSession, StudyAssistantMessage,
    PlacementPlanCompletion, LearningActivity,
)
import subprocess
import sys
import tempfile
import os
from datetime import date, timedelta
BASE_DIR = Path(__file__).resolve().parent

INTERVIEW_TOPICS = [
    ("Tell me about yourself", "Build a concise introduction that connects your background, strongest skill, and the role you want."),
    ("Project deep dive", "Explain a project you worked on: the problem, your contribution, one technical decision, and the result."),
    ("Problem solving", "Describe a difficult problem you faced. Walk through how you understood it, tested options, and reached a solution."),
    ("Teamwork", "Tell a story about working with someone whose approach differed from yours. How did you reach a good outcome?"),
    ("Conflict and feedback", "Share a time you received challenging feedback or disagreed with a teammate. What did you do next?"),
    ("Strengths and growth", "Name a strength that helps you at work and a skill you are actively improving. Give a specific example of each."),
    ("Role motivation", "Why does this role interest you, and what would you aim to learn or contribute in your first few months?"),
    ("Technical explanation", "Choose a technical concept you know well and explain it clearly to a curious non-specialist. Include a simple example."),
    ("Ownership", "Describe a time you took initiative without being asked. What changed because you acted?"),
    ("Reflection", "Think of a mistake or setback. What did you learn, and what do you do differently now?"),
]

INTERVIEW_CHALLENGES = [
    {"level": level, "topic": INTERVIEW_TOPICS[(level - 1) % len(INTERVIEW_TOPICS)][0],
     "prompt": INTERVIEW_TOPICS[(level - 1) % len(INTERVIEW_TOPICS)][1],
     "focus": ["Use a clear beginning, middle, and takeaway.", "Be specific about your own actions and impact.", "Keep your answer focused and natural."][((level - 1) // len(INTERVIEW_TOPICS)) % 3]}
    for level in range(1, 101)
]

PLACEMENT_WEEK = [
    {"aptitude": "Quantitative Aptitude", "code": "Arrays", "interview": "Project deep dive", "english": "conversation"},
    {"aptitude": "Logical Reasoning", "code": "Strings", "interview": "Tell me about yourself", "english": "grammar"},
    {"aptitude": "Python Programming", "code": "Algorithms", "interview": "Problem solving", "english": "interview"},
    {"aptitude": "DBMS", "code": "Basics", "interview": "Teamwork", "english": "vocabulary"},
    {"aptitude": "Computer Networks", "code": "Arrays", "interview": "Conflict and feedback", "english": "conversation"},
    {"aptitude": "Quantitative Aptitude", "code": "Algorithms", "interview": "Role motivation", "english": "interview"},
    {"aptitude": "Logical Reasoning", "code": "Strings", "interview": "Reflection", "english": "grammar"},
]

APTITUDE_GUIDES = {
    "Quantitative Aptitude": {
        "tagline": "Build speed with clear steps and smart estimation.",
        "tips": ["Translate the prompt into a simple equation before calculating.", "Estimate the answer range to catch arithmetic slips.", "For percentages, compare the change with the original value."],
        "interview_tip": "Explain your approach aloud before giving the final number.",
    },
    "Logical Reasoning": {
        "tagline": "Spot patterns, test conditions, and eliminate contradictions.",
        "tips": ["Write each condition down instead of holding it in memory.", "Check one rule at a time when testing an option.", "For sequences, compare differences and alternating positions."],
        "interview_tip": "State the rule you used so the interviewer can follow your reasoning.",
    },
    "Python Programming": {
        "tagline": "Practise core syntax, data structures, and readable solutions.",
        "tips": ["Trace a small input by hand before choosing an approach.", "Know when to use lists, dictionaries, sets, and tuples.", "Check empty input, duplicates, and boundary values."],
        "interview_tip": "Discuss time complexity and one edge case after solving.",
    },
    "Operating Systems": {
        "tagline": "Review processes, memory, scheduling, and synchronization.",
        "tips": ["Contrast related concepts, such as process vs. thread.", "Use a small timeline to reason through scheduling questions.", "Connect each definition to a practical system example."],
        "interview_tip": "Define the concept, explain the trade-off, then give an example.",
    },
    "DBMS": {
        "tagline": "Strengthen SQL, keys, normalization, and transaction concepts.",
        "tips": ["Draw a tiny table to reason about joins and keys.", "Know what each normal form prevents.", "Remember ACID by describing what can fail during a transaction."],
        "interview_tip": "Explain how your database design protects data consistency.",
    },
    "Computer Networks": {
        "tagline": "Connect network layers, protocols, and real request flows.",
        "tips": ["Trace what happens from entering a URL to receiving a page.", "Compare TCP and UDP by reliability and use case.", "Use the OSI or TCP/IP layers to organize an explanation."],
        "interview_tip": "Walk through a real example, such as a browser request.",
    },
}

app = Flask(__name__)


def record_learning_activity(user, category):
    """Record a completed learning action and update the learner's daily streak."""
    today = date.today()
    last_practice = user.english_last_practice_date
    existing = LearningActivity.query.filter_by(
        user_id=user.id, category=category, activity_date=today
    ).first()
    if not existing:
        db.session.add(LearningActivity(
            user_id=user.id, category=category, activity_date=today
        ))
    if last_practice != today:
        user.english_practice_streak = (
            user.english_practice_streak + 1
            if last_practice == today - timedelta(days=1) else 1
        )
        user.english_last_practice_date = today
    db.session.commit()


app.config.from_object(Config)

# Initialize the database.
db.init_app(app)

# Configure login sessions.
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# Create the database tables.
with app.app_context():
    (BASE_DIR / "instance").mkdir(exist_ok=True)
    db.create_all()


@app.route("/")
def home():
    done_categories = set()
    streak = 0
    if current_user.is_authenticated:
        done_categories = {
            item.category for item in LearningActivity.query.filter_by(
                user_id=current_user.id, activity_date=date.today()
            ).all()
        }
        streak = current_user.english_practice_streak
    core_categories = {"aptitude", "coding", "interview", "communication"}
    completed = done_categories & core_categories
    return render_template(
        "index.html",
        today_progress_completed=len(completed),
        today_progress_percent=round(len(completed) / len(core_categories) * 100),
        learning_streak=streak,
        is_authenticated=current_user.is_authenticated,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill in all required fields.", "error")

        elif len(name) > 100 or len(email) > 150:
            flash("Name or email is too long.", "error")

        elif "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            flash("Please enter a valid email address.", "error")

        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")

        elif password != confirm_password:
            flash("Passwords do not match.", "error")

        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")

        else:
            user = User(name=name, email=email)
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


def make_password_reset_token(user):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(
        {"user_id": user.id, "password_hash": user.password_hash},
        salt="learnsphere-password-reset",
    )


def send_password_reset_email(user, reset_url):
    mail_server = current_app.config.get("MAIL_SERVER")
    sender = current_app.config.get("MAIL_DEFAULT_SENDER")
    if not mail_server or not sender:
        raise RuntimeError("SMTP mail settings are missing.")

    message = EmailMessage()
    message["Subject"] = "Reset your LearnSphere AI password"
    message["From"] = sender
    message["To"] = user.email
    message.set_content(
        "We received a request to reset your LearnSphere AI password.\n\n"
        f"Use this secure link within one hour:\n{reset_url}\n\n"
        "If you did not request this change, you can ignore this email. "
        "Your password will remain unchanged."
    )

    port = current_app.config["MAIL_PORT"]
    timeout = 15
    if current_app.config.get("MAIL_USE_SSL"):
        mail_client = smtplib.SMTP_SSL(
            mail_server,
            port,
            context=ssl.create_default_context(),
            timeout=timeout,
        )
    else:
        mail_client = smtplib.SMTP(mail_server, port, timeout=timeout)

    with mail_client as server:
        if not current_app.config.get("MAIL_USE_SSL") and current_app.config.get("MAIL_USE_TLS"):
            server.starttls(context=ssl.create_default_context())
        username = current_app.config.get("MAIL_USERNAME")
        password = current_app.config.get("MAIL_PASSWORD")
        if username and password:
            server.login(username, password)
        server.send_message(message)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first() if email else None
        if user:
            try:
                token = make_password_reset_token(user)
                reset_url = url_for("reset_password", token=token, _external=True)
                send_password_reset_email(user, reset_url)
            except Exception:
                app.logger.warning("Password reset email delivery failed.")
        flash(
            "If an account with that email exists, a password reset link will be sent.",
            "success",
        )
        return redirect(url_for("forgot_password"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        payload = serializer.loads(
            token,
            salt="learnsphere-password-reset",
            max_age=current_app.config["PASSWORD_RESET_MAX_AGE"],
        )
        user = db.session.get(User, int(payload.get("user_id", 0)))
        if not user or payload.get("password_hash") != user.password_hash:
            raise BadSignature("Password reset token is no longer valid.")
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        flash("That password reset link is invalid or expired. Request a new one.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Choose a password with at least 8 characters.", "error")
        elif password != confirm_password:
            flash("The passwords do not match.", "error")
        else:
            user.set_password(password)
            db.session.commit()
            flash("Your password has been reset. You can now log in.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/dashboard")
@login_required
def dashboard():
    # Get quiz attempts belonging to the logged-in student
    attempts = QuizAttempt.query.filter_by(
        user_id=current_user.id
    ).order_by(
        QuizAttempt.created_at.desc()
    ).all()

    # Calculate performance statistics
    total_quizzes = len(attempts)

    average_percentage = round(
        sum(attempt.percentage for attempt in attempts) / total_quizzes,
        1
    ) if total_quizzes else 0

    best_percentage = max(
        (attempt.percentage for attempt in attempts),
        default=0
    )

    topics_practised = len({
        attempt.topic for attempt in attempts
    })

    total_questions = sum(
        attempt.total_questions for attempt in attempts
    )
    completed_questions = sum(
        attempt.correct_answers for attempt in attempts
    )

    progress_percentage = round(
        (completed_questions / total_questions) * 100
    ) if total_questions else 0

    challenge_completions = InterviewChallengeCompletion.query.filter_by(
        user_id=current_user.id
    ).count()
    interview_practice_count = InterviewPracticeSession.query.filter_by(
        user_id=current_user.id
    ).count()
    placement_tasks_done = PlacementPlanCompletion.query.filter_by(
        user_id=current_user.id,
        plan_date=date.today(),
    ).count()
    next_challenge_level = min(challenge_completions + 1, 100)

    return render_template(
        "dashboard.html",
        attempts=attempts,
        total_quizzes=total_quizzes,
        average_percentage=average_percentage,
        best_percentage=best_percentage,
        topics_practised=topics_practised,
        total_questions=total_questions,
        completed_questions=completed_questions,
        progress_percentage=progress_percentage,
        challenge_completions=challenge_completions,
        challenge_percentage=challenge_completions,
        interview_practice_count=interview_practice_count,
        placement_tasks_done=placement_tasks_done,
        next_challenge_level=next_challenge_level
    )


@app.route("/placement-plan")
@login_required
def placement_plan():
    today = date.today()
    focus = PLACEMENT_WEEK[today.weekday()]
    attempts = QuizAttempt.query.filter_by(user_id=current_user.id).all()
    topic_scores = {}
    for attempt in attempts:
        topic_scores.setdefault(attempt.topic, []).append(attempt.percentage)
    weakest_topic = min(
        topic_scores,
        key=lambda topic: sum(topic_scores[topic]) / len(topic_scores[topic]),
    ) if topic_scores else focus["aptitude"]
    weakest_average = round(sum(topic_scores[weakest_topic]) / len(topic_scores[weakest_topic])) if topic_scores else None
    interview_prompt = dict(INTERVIEW_TOPICS).get(focus["interview"], INTERVIEW_TOPICS[0][1])

    tasks = [
        {"key": "aptitude", "title": f"Sharpen {weakest_topic}",
         "detail": f"Complete a five-question quiz. Your previous average is {weakest_average}%—use today's attempt to focus on accuracy." if weakest_average is not None else "Take a five-question placement quiz to establish your starting point.",
         "minutes": 10, "action": "Open Aptitude Arena", "href": url_for("aptitude")},
        {"key": "coding", "title": f"Solve a {focus['code']} coding problem",
         "detail": "Generate a Python challenge, run your solution, and check it against a sample case.",
         "minutes": 15, "action": "Open Code Lab", "href": url_for("code_lab")},
        {"key": "interview", "title": f"Practise: {focus['interview']}",
         "detail": interview_prompt,
         "minutes": 10, "action": "Open Interview Hub", "href": url_for("interview_hub")},
        {"key": "communication", "title": f"English {focus['english']} warm-up",
         "detail": "Write or speak a short response, then apply one suggestion from your coach.",
         "minutes": 5, "action": "Open English Coach", "href": url_for("english_coach_page")},
    ]
    completed_keys = {
        item.task_key for item in PlacementPlanCompletion.query.filter_by(
            user_id=current_user.id, plan_date=today
        ).all()
    }
    return render_template(
        "placement_plan.html",
        tasks=tasks,
        completed_keys=completed_keys,
        completed_count=len(completed_keys),
        plan_date=today,
        day_name=today.strftime("%A"),
        total_minutes=sum(task["minutes"] for task in tasks),
    )


@app.route("/placement-plan/complete/<task_key>", methods=["POST"])
@login_required
def complete_placement_task(task_key):
    allowed_tasks = {"aptitude", "coding", "interview", "communication"}
    if task_key not in allowed_tasks:
        return jsonify({"error": "Unknown placement task."}), 404
    today = date.today()
    existing = PlacementPlanCompletion.query.filter_by(
        user_id=current_user.id,
        plan_date=today,
        task_key=task_key,
    ).first()
    if not existing:
        db.session.add(PlacementPlanCompletion(
            user_id=current_user.id,
            plan_date=today,
            task_key=task_key,
        ))
        record_learning_activity(current_user, task_key)
    else:
        db.session.commit()
    flash("Placement plan progress saved.", "success")
    return redirect(url_for("placement_plan"))


@app.route("/interview-hub")
@login_required
def interview_hub():
    selected_topic = request.values.get("topic", INTERVIEW_TOPICS[0][0])
    allowed_topics = {title: prompt for title, prompt in INTERVIEW_TOPICS}
    if selected_topic not in allowed_topics:
        selected_topic = INTERVIEW_TOPICS[0][0]
    prompt = allowed_topics[selected_topic]
    error_message = None
    review = None
    response_draft = ""

    if request.method == "POST":
        response = request.form.get("response", "").strip()
        response_draft = response
        if len(response) < 20:
            error_message = "Add a little more detail before saving your practice answer."
        else:
            words = response.split()
            lowered = f" {response.lower()} "
            signals = {
                "A specific example": len(words) >= 50,
                "Your personal contribution": any(term in lowered for term in (" i ", " my ", "me ")),
                "A result or impact": any(term in lowered for term in ("result", "impact", "improved", "increased", "reduced", "saved", "delivered")),
                "A takeaway": any(term in lowered for term in ("learned", "lesson", "next time", "now i", "since then")),
            }
            practice = InterviewPracticeSession(
                user_id=current_user.id,
                topic=selected_topic,
                prompt=prompt,
                response=response,
                word_count=len(words),
            )
            db.session.add(practice)
            record_learning_activity(current_user, "interview")
            review = {
                "signals": signals,
                "word_count": len(words),
                "saved": True,
            }

    history = InterviewPracticeSession.query.filter_by(
        user_id=current_user.id
    ).order_by(InterviewPracticeSession.created_at.desc()).limit(5).all()
    return render_template(
        "interview_hub.html",
        topics=INTERVIEW_TOPICS,
        selected_topic=selected_topic,
        prompt=prompt,
        error_message=error_message,
        review=review,
        response_draft=response_draft,
        history=history,
    )


@app.route("/study-assistant")
@login_required
def study_assistant():
    messages = StudyAssistantMessage.query.filter_by(
        user_id=current_user.id
    ).order_by(StudyAssistantMessage.created_at.desc()).limit(40).all()[::-1]
    return render_template("study_assistant.html", messages=messages)


@app.route("/ai-coach")
@login_required
def ai_coach():
    messages = StudyAssistantMessage.query.filter_by(
        user_id=current_user.id,
        mode="career",
    ).order_by(StudyAssistantMessage.created_at.desc()).limit(30).all()[::-1]
    return render_template("ai_coach.html", messages=messages)


@app.route("/ai-coach/respond", methods=["POST"])
@login_required
def ai_coach_respond():
    data = request.get_json(silent=True) or {}
    role = data.get("role", "General placement")
    timeline = data.get("timeline", "Exploring opportunities")
    focus = data.get("focus", "Overall preparation")
    message = data.get("message", "")
    if not all(isinstance(value, str) for value in (role, timeline, focus, message)):
        return jsonify({"error": "Please enter a valid coaching request."}), 400
    role, timeline, focus, message = (value.strip() for value in (role, timeline, focus, message))
    if not message:
        return jsonify({"error": "Choose a suggested prompt or tell your coach what you need help with."}), 400
    if len(message) > 6000 or len(role) > 100 or len(timeline) > 100 or len(focus) > 100:
        return jsonify({"error": "Please shorten your coaching request and profile details."}), 400

    history_rows = StudyAssistantMessage.query.filter_by(
        user_id=current_user.id,
        mode="career",
    ).order_by(StudyAssistantMessage.id.desc()).limit(10).all()[::-1]
    history = [{"role": item.role, "content": item.content} for item in history_rows]
    context = f"Target role: {role or 'General placement'}; timeline: {timeline or 'Not specified'}; current focus: {focus or 'Overall preparation'}"
    try:
        answer = generate_study_reply("career", context, message, history)
        db.session.add_all([
            StudyAssistantMessage(user_id=current_user.id, role="user", mode="career", content=message),
            StudyAssistantMessage(user_id=current_user.id, role="assistant", mode="career", content=answer),
        ])
        db.session.commit()
        record_learning_activity(current_user, "study")
        return jsonify({"answer": answer})
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception("AI Coach request failed")
        return jsonify({"error": "Your AI Coach is temporarily unavailable. Check the Gemini configuration and try again."}), 503


@app.route("/study-assistant/respond", methods=["POST"])
@login_required
def study_assistant_respond():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "tutor")
    subject = data.get("subject", "General study")
    message = data.get("message", "")

    if not isinstance(mode, str) or not isinstance(subject, str) or not isinstance(message, str):
        return jsonify({"error": "Please enter a valid study request."}), 400
    subject = subject.strip()[:120] or "General study"
    message = message.strip()
    if not message:
        return jsonify({"error": "Enter a topic, question, or notes to get started."}), 400
    if len(message) > 6000:
        return jsonify({"error": "Please keep your message under 6,000 characters."}), 400

    history_rows = StudyAssistantMessage.query.filter_by(
        user_id=current_user.id
    ).order_by(StudyAssistantMessage.id.desc()).limit(10).all()[::-1]
    history = [{"role": item.role, "content": item.content} for item in history_rows]
    try:
        answer = generate_study_reply(mode, subject, message, history)
        db.session.add_all([
            StudyAssistantMessage(user_id=current_user.id, role="user", mode=mode, content=message),
            StudyAssistantMessage(user_id=current_user.id, role="assistant", mode=mode, content=answer),
        ])
        db.session.commit()
        record_learning_activity(current_user, "study")
        return jsonify({"answer": answer, "mode": mode})
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception("Study Assistant request failed")
        return jsonify({
            "error": "Study Assistant is temporarily unavailable. Check that GEMINI_API_KEY is configured, then try again."
        }), 503


@app.route("/challenges")
@login_required
def challenges():
    completed_levels = {row.level for row in InterviewChallengeCompletion.query.filter_by(user_id=current_user.id).all()}
    next_level = next((level for level in range(1, 101) if level not in completed_levels), 100)
    return render_template("challenges.html", challenges=INTERVIEW_CHALLENGES,
                           completed_levels=completed_levels, next_level=next_level)


@app.route("/challenges/<int:level>", methods=["GET", "POST"])
@login_required
def challenge_level(level):
    if not 1 <= level <= 100:
        return redirect(url_for("challenges"))
    completed_levels = {row.level for row in InterviewChallengeCompletion.query.filter_by(user_id=current_user.id).all()}
    next_level = next((item for item in range(1, 101) if item not in completed_levels), 100)
    if level not in completed_levels and level > next_level:
        flash("Complete the previous level to unlock this challenge.", "error")
        return redirect(url_for("challenges"))

    challenge = INTERVIEW_CHALLENGES[level - 1]
    error_message = None
    if request.method == "POST":
        response = request.form.get("response", "").strip()
        if len(response) < 20:
            error_message = "Write at least 20 characters so you can review a complete answer."
        elif level not in completed_levels:
            db.session.add(InterviewChallengeCompletion(user_id=current_user.id, level=level, response=response))
            record_learning_activity(current_user, "interview")
            flash(f"Level {level} completed! Your dashboard progress is updated.", "success")
            return redirect(url_for("challenges"))
    return render_template("challenge_level.html", challenge=challenge,
                           completed=level in completed_levels, error_message=error_message)
@app.route("/aptitude", methods=["GET", "POST"])
@login_required
def aptitude():
    questions = []
    topic = "Quantitative Aptitude"
    difficulty = "Easy"
    timed = False
    error_message = None

    if request.method == "POST":
        topic = request.form.get("topic", "").strip()
        difficulty = request.form.get("difficulty", "").strip()
        timed = request.form.get("timed") == "on"

        allowed_topics = [
            "Quantitative Aptitude",
            "Logical Reasoning",
            "Python Programming",
            "Operating Systems",
            "DBMS",
            "Computer Networks",
        ]

        allowed_difficulties = ["Easy", "Medium", "Hard"]

        if topic not in allowed_topics:
            error_message = "Please select a valid topic."

        elif difficulty not in allowed_difficulties:
            error_message = "Please select a valid difficulty."

        else:
            try:
                questions = generate_questions(
                    topic=topic,
                    difficulty=difficulty,
                    count=5,
                )
            except Exception:
                app.logger.exception("AI question generation failed.")
                error_message = (
                    "We couldn't generate questions right now. "
                    "Please try again shortly."
                )

    return render_template(
        "aptitude.html",
        questions=questions,
        topic=topic,
        difficulty=difficulty,
        guide=APTITUDE_GUIDES.get(topic, APTITUDE_GUIDES["Quantitative Aptitude"]),
        timed=timed,
        error_message=error_message,
    )

@app.route("/code-lab", methods=["GET", "POST"])
@login_required
def code_lab():
    challenge = None
    error_message = None
    language = request.form.get("language", "Python")
    difficulty = request.form.get("difficulty", "Easy")
    topic = request.form.get("topic", "Basics")

    if request.method == "POST":
        allowed_difficulties = {"Easy", "Medium", "Hard"}
        allowed_topics = {"Basics", "Arrays", "Strings", "Algorithms"}
        if language != "Python":
            error_message = "The Code Lab runner currently supports Python."
        elif difficulty not in allowed_difficulties or topic not in allowed_topics:
            error_message = "Choose a valid difficulty and topic."
        else:
            try:
                challenge = generate_coding_challenge(
                    language=language,
                    difficulty=difficulty,
                    topic=topic
                )
            except Exception:
                app.logger.exception("Code Lab question generation failed")
                error_message = (
                    "Unable to generate a challenge right now. "
                    "Please check your API quota and configuration, then try again."
                )

    return render_template(
        "code_lab.html",
        challenge=challenge,
        error_message=error_message,
        language=language,
        difficulty=difficulty,
        topic=topic,
    )
@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have logged out successfully.", "success")
    return redirect(url_for("home"))

@app.route("/save-quiz-result", methods=["POST"])
@login_required
def save_quiz_result():
    data = request.get_json(silent=True) or {}

    try:
        topic = str(data.get("topic", "")).strip()
        total = int(data.get("total_questions", 0))
        correct = int(data.get("correct_answers", -1))

        allowed_topics = [
            "Quantitative Aptitude",
            "Logical Reasoning",
            "Python Programming",
            "Operating Systems",
            "DBMS",
            "Computer Networks",
        ]

        if topic not in allowed_topics:
            return {"error": "Invalid topic."}, 400

        if total != 5 or not 0 <= correct <= total:
            return {"error": "Invalid quiz result."}, 400

        percentage = round((correct / total) * 100, 2)

        attempt = QuizAttempt(
            user_id=current_user.id,
            topic=topic,
            total_questions=total,
            correct_answers=correct,
            percentage=percentage,
        )

       
        db.session.add(attempt)
        db.session.commit()

        record_learning_activity(current_user, "aptitude")

        return {
            "message": "Quiz result saved successfully!",
            "score": f"{correct}/{total}",
            "percentage": percentage,
        }, 201


    except (ValueError, TypeError):
        return {"error": "Invalid result data."}, 400

    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to save quiz result.")
        return {"error": "Could not save quiz result."}, 500

@app.route("/run-code", methods=["POST"])
@login_required
def run_code():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return {"output": "", "error": "Send code and input as a JSON object."}, 400
    code = data.get("code", "")
    code_input = data.get("input", "")

    if not isinstance(code, str) or not isinstance(code_input, str):
        return {"output": "", "error": "Code and input must be text."}, 400

    if len(code) > 20000 or len(code_input) > 5000:
        return {"output": "", "error": "Code is limited to 20,000 characters and input to 5,000 characters."}, 400

    if not code.strip():
        return {"output": "", "error": "Please write some Python code."}, 400

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "solution.py")

            with open(file_path, "w", encoding="utf-8") as file:
                file.write(code)

            result = subprocess.run(
                [sys.executable, "-I", file_path],
                input=code_input,
                capture_output=True,
                text=True,
                timeout=5,
                cwd=temp_dir,
            )

            return {
                "output": result.stdout[:100000],
                "error": result.stderr[:100000],
                "returncode": result.returncode,
                "truncated": len(result.stdout) > 100000 or len(result.stderr) > 100000,
            }

    except subprocess.TimeoutExpired:
        return {
            "output": "",
            "error": "Time limit exceeded. Your code took too long."
        }
    except Exception:
        app.logger.exception("Code execution failed")
        return {
            "output": "",
            "error": "Unable to run code. Please try again."
        }, 500


@app.route("/coding-challenge-completed", methods=["POST"])
@login_required
def coding_challenge_completed():
    try:
        record_learning_activity(current_user, "coding")

        return jsonify({
            "success": True,
            "streak": current_user.english_practice_streak,
            "message": "Coding practice saved to your learning streak."
        })

    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to update coding streak.")

        return jsonify({
            "success": False,
            "error": "Unable to update your daily streak."
        }), 500

@app.route("/english-coach", methods=["POST"])
@login_required
def english_coach():
    data = request.get_json(silent=True) or {}

    message = data.get("message", "")
    mode = data.get("mode", "conversation")
    level = data.get("level", "adaptive")

    if not isinstance(message, str):
        return jsonify({"error": "Please enter a valid message."}), 400

    if not isinstance(mode, str):
        mode = "conversation"

    if not isinstance(level, str):
        level = "adaptive"

    try:
        feedback = get_english_feedback(message, mode, level)
        record_learning_activity(current_user, "communication")
        return jsonify({"feedback": feedback})

    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    except Exception:
        app.logger.exception("English Coach failed")
        return jsonify({
            "error": "English Coach is temporarily unavailable. Please try again."
        }), 503

@app.route("/english-coach-page")
@login_required
def english_coach_page():
    return render_template("english_coach.html")


@app.route("/pronunciation-feedback", methods=["POST"])
@login_required
def pronunciation_feedback():
    data = request.get_json(silent=True) or {}

    sentence = data.get("sentence", "")
    level = data.get("level", "adaptive")

    if not isinstance(sentence, str):
        return jsonify({"error": "Please enter a valid sentence."}), 400

    if not isinstance(level, str):
        level = "adaptive"

    try:
        feedback = get_pronunciation_practice_feedback(
            sentence, level
        )
        record_learning_activity(current_user, "communication")
        return jsonify(feedback)

    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    except Exception:
        app.logger.exception("Pronunciation feedback failed")
        return jsonify({
            "error": "AI feedback is temporarily unavailable. Please try again."
        }), 503


if __name__ == "__main__":
    app.run(debug=True)


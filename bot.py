#!/usr/bin/env python3
"""
P6 Tutor Bot with Firebase Integration
Bina Bangsa School Curriculum + Chinese
Reads from Firebase database + Claude fallback
"""

import os
import json
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic
import firebase_admin
from firebase_admin import credentials, db

# ============================================
# CONFIG
# ============================================

DASHBOARD_URL = "https://mypalstutorbot-dashboard.vercel.app"

# ============================================
# INITIALIZE CLIENTS
# ============================================

# Firebase
try:
    firebase_creds_env = os.getenv('FIREBASE_CREDENTIALS_JSON')
    if firebase_creds_env:
        cred = credentials.Certificate(json.loads(firebase_creds_env))
    else:
        cred = credentials.Certificate('firebase-credentials.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://mypalstutorbot-default-rtdb.asia-southeast1.firebasedatabase.app'
    })
    FIREBASE_AVAILABLE = True
    print("✅ Firebase connected")
except Exception as e:
    print(f"⚠️ Firebase unavailable: {e}")
    FIREBASE_AVAILABLE = False

# Anthropic
anthropic = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

# ============================================
# IN-MEMORY STORAGE
# ============================================

student_data = {}

def get_student(user_id):
    if user_id not in student_data:
        student_data[user_id] = {
            'name': 'Student',
            'stars': 0,
            'level': 'Bronze',
            'progress': {},
            'badges': [],
            'conversation_history': []
        }
    return student_data[user_id]

# ============================================
# SUBJECT / TOPIC MAP (for flexible topic requests)
# ============================================

SUBJECT_MAP = {
    'math': ['fractions', 'ratio', 'percentage', 'algebra', 'geometry', 'data', 'time'],
    'science': ['photosynthesis', 'ecosystems', 'food_chain', 'digestion', 'reproduction', 'weather', 'forces', 'machines', 'electricity'],
    'english': ['grammar', 'vocabulary', 'comprehension', 'tenses', 'punctuation'],
    'indonesian': ['vocabulary', 'grammar', 'stories', 'poetry', 'spelling'],
    'chinese': ['characters', 'vocabulary', 'grammar', 'radicals', 'listening'],
}
ALL_TOPIC_PAIRS = [(subject, topic) for subject, topics in SUBJECT_MAP.items() for topic in topics]

def find_subject_for_topic(topic):
    """Find which subject a bare topic name belongs to, e.g. 'fractions' -> 'math'"""
    for subject, topics in SUBJECT_MAP.items():
        if topic in topics:
            return subject
    return None

def resolve_topics(spec_tokens):
    """Turn a list of raw tokens (topic names and/or subject names, e.g. ['math'] or ['ratio','fraction'])
    into a deduped list of (subject, topic) pairs to quiz on. Empty input -> one random topic."""
    resolved = []
    for tok in spec_tokens:
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok in SUBJECT_MAP:
            for t in SUBJECT_MAP[tok]:
                resolved.append((tok, t))
        else:
            subj = find_subject_for_topic(tok)
            resolved.append((subj or tok, tok))

    if not resolved:
        resolved = [random.choice(ALL_TOPIC_PAIRS)]

    # dedupe, preserve order
    seen = set()
    out = []
    for pair in resolved:
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out

def split_count(total, n):
    """Split `total` questions as evenly as possible across `n` topics"""
    if n <= 0:
        return []
    base = total // n
    rem = total % n
    return [base + (1 if i < rem else 0) for i in range(n)]

# ============================================
# FIREBASE FUNCTIONS
# ============================================

def get_firebase_questions(topic, subject=None):
    """Fetch questions from Firebase at /questions/{subject}/{topic}"""
    if not FIREBASE_AVAILABLE:
        return None

    try:
        subj = subject or find_subject_for_topic(topic) or topic
        path = f'/questions/{subj}/{topic}'
        ref = db.reference(path)
        data = ref.get()

        if data:
            return data
    except Exception as e:
        print(f"Firebase error: {e}")

    return None

def fetch_questions_from_firebase(topic, count=5, difficulty='mixed', subject=None):
    """Get questions from Firebase with fallback"""
    firebase_data = get_firebase_questions(topic, subject)

    if not firebase_data:
        return None

    questions = []

    # Try the requested single difficulty first (adaptive mode)
    if difficulty != 'mixed' and difficulty in firebase_data:
        level_questions = list(firebase_data[difficulty].values()) if isinstance(firebase_data[difficulty], dict) else firebase_data[difficulty]
        questions.extend(level_questions)

    # Fall back to a mixed blend if no single-difficulty questions were found
    if not questions:
        for level in ['easy', 'medium', 'hard']:
            if level in firebase_data:
                level_questions = list(firebase_data[level].values()) if isinstance(firebase_data[level], dict) else firebase_data[level]
                questions.extend(level_questions[:count//3 + 1])

    if not questions:
        return None

    return random.sample(questions, min(count, len(questions)))

def get_next_difficulty(student, topic):
    """Decide difficulty for the next quiz based on the student's last score on this topic"""
    prog = student.get('progress', {}).get(topic)
    if not prog or 'last_score' not in prog:
        return 'mixed'  # first attempt on this topic: give a mixed set

    last_score = prog['last_score']
    if last_score >= 85:
        return 'hard'
    elif last_score >= 60:
        return 'medium'
    else:
        return 'easy'

def save_progress_to_firebase(user_id, student):
    """Push this student's stars/level/progress to Firebase so the web dashboard can read it"""
    if not FIREBASE_AVAILABLE:
        return
    try:
        db.reference(f'/students/{user_id}').set({
            'name': student.get('name', 'Student'),
            'stars': student.get('stars', 0),
            'level': student.get('level', 'Bronze'),
            'progress': student.get('progress', {}),
            'badges': student.get('badges', []),
        })
    except Exception as e:
        print(f"⚠️ Firebase write error: {e}")

# ============================================
# CLAUDE FALLBACK
# ============================================

def generate_questions_claude(topic, count=5, language='english'):
    """Generate questions using Claude API"""
    prompt = f"""Generate {count} P6 Bina Bangsa School {topic.title()} quiz questions in {language}.
    
    Format ONLY as JSON array, no other text:
    [
      {{
        "q": "Question text",
        "a": "The correct option's exact text, copied verbatim from one of the 4 items in options below (NOT a letter like A/B/C/D)",
        "type": "ABCD",
        "options": ["first answer choice", "second answer choice", "third answer choice", "fourth answer choice"],
        "exp": "Explanation"
      }}
    ]
    """
    
    response = anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    try:
        text = response.content[0].text.strip()
        # Remove markdown code blocks if present
        if text.startswith("```"):
            text = text[7:-3] if text.endswith("```") else text[7:]
        return json.loads(text)
    except:
        return []

def detect_quiz_intent(text):
    """Ask Claude whether a free-chat message is asking for practice questions, and extract topics/count if so."""
    known_topics = ', '.join(sorted(set(t for topics in SUBJECT_MAP.values() for t in topics)))
    known_subjects = ', '.join(SUBJECT_MAP.keys())
    prompt = f"""A student is chatting with a P6 tutor bot. Decide if this message is asking for practice quiz questions.

Message: "{text}"

Known subjects: {known_subjects}
Known specific topics: {known_topics}

If it IS a request for questions, extract:
- topics: a list using ONLY the exact names above (subject names and/or specific topic names) that match what the student asked for. Empty list if no specific topic was named (student wants something random).
- count: how many questions total were asked for (a number). Default to 5 if not stated.

Respond with ONLY compact JSON, nothing else:
{{"is_quiz_request": true, "topics": ["ratio", "fractions"], "count": 10}}
or
{{"is_quiz_request": false, "topics": [], "count": 0}}
"""
    try:
        response = anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        out = response.content[0].text.strip()
        if out.startswith("```"):
            out = out.strip('`')
            if out.lower().startswith('json'):
                out = out[4:]
        return json.loads(out)
    except Exception as e:
        print(f"Intent detection error: {e}")
        return {"is_quiz_request": False, "topics": [], "count": 0}

# ============================================
# QUESTION HANDLING
# ============================================

def format_question(question, index=1):
    """Format question for display"""
    q_text = question.get('q', '')
    options = question.get('options', [])
    
    if options and len(options) == 4:
        msg = f"*Question {index}:* {q_text}\n\n"
        msg += f"A) {options[0]}\n"
        msg += f"B) {options[1]}\n"
        msg += f"C) {options[2]}\n"
        msg += f"D) {options[3]}\n"
        return msg
    else:
        return f"*Question {index}:* {q_text}\n"

def score_answer(user_answer, correct_answer):
    """Check if answer is correct"""
    user_ans = user_answer.strip().upper()
    correct_ans = correct_answer.strip().upper()
    return user_ans == correct_ans

def get_correct_answer_info(question):
    """Work out the correct option LETTER (and its text) for a question.

    Questions from Firebase store q['a'] as the correct answer's TEXT
    (e.g. "3/4"), matching one of the 4 items in q['options']. Questions
    generated live by Claude sometimes instead return q['a'] as a bare
    letter (A/B/C/D). This handles both shapes so scoring never mismatches
    a letter against a value (or vice versa).
    """
    raw = str(question.get('a', '')).strip()
    options = question.get('options', [])

    # Case 1: 'a' is the answer's text - find which option it matches
    for idx, opt in enumerate(options):
        if str(opt).strip().upper() == raw.upper():
            return chr(65 + idx), str(opt)

    # Case 2: 'a' is already a bare letter A-D
    if raw.upper() in ('A', 'B', 'C', 'D') and len(options) == 4:
        idx = ord(raw.upper()) - 65
        return raw.upper(), str(options[idx])

    # Fallback: couldn't resolve against options, just return what we have
    return raw.upper(), raw

async def send_quiz(update, student, topic_pairs, count):
    """Build a quiz across one or more (subject, topic) pairs, splitting count between them,
    using Firebase + adaptive difficulty where possible and falling back to Claude otherwise."""
    n = len(topic_pairs)
    counts = split_count(count, n)

    all_questions = []
    for (subject, topic), per_count in zip(topic_pairs, counts):
        if per_count <= 0:
            continue
        difficulty = get_next_difficulty(student, topic)
        qs = fetch_questions_from_firebase(topic, per_count, difficulty, subject) if FIREBASE_AVAILABLE else None
        if not qs:
            qs = generate_questions_claude(topic, per_count)
        if qs:
            for q in qs:
                q['_topic'] = topic
            all_questions.extend(qs)

    if not all_questions:
        await update.message.reply_text("❌ Could not generate questions. Try another topic.")
        return

    # Store for scoring
    student['current_questions'] = all_questions
    student['current_topics'] = [t for _, t in topic_pairs]
    student['current_topic'] = student['current_topics'][0]  # fallback label
    student['answers'] = []

    topic_labels = ', '.join(t.replace('_', ' ').title() for _, t in topic_pairs)
    header = f"*QUIZ: {topic_labels} - {len(all_questions)} Questions*\n\n"

    # Split into multiple Telegram messages if it gets long (Telegram's limit is ~4096 chars)
    messages = []
    current_msg = header
    for i, q in enumerate(all_questions, 1):
        block = format_question(q, i) + "\n"
        if len(current_msg) + len(block) > 3500:
            messages.append(current_msg)
            current_msg = ""
        current_msg += block
    current_msg += "\n_Send answers as: Q1: A, Q2: B, Q3: C, etc_"
    messages.append(current_msg)

    for msg in messages:
        await update.message.reply_text(msg, parse_mode='Markdown')

# ============================================
# REWARD SYSTEM
# ============================================

def calculate_stars(score_percentage):
    """Convert score to stars"""
    if score_percentage >= 90:
        return 15
    elif score_percentage >= 80:
        return 12
    elif score_percentage >= 70:
        return 10
    elif score_percentage >= 60:
        return 7
    else:
        return 3

def update_level(stars):
    """Update level based on stars"""
    if stars >= 500:
        return 'Platinum'
    elif stars >= 300:
        return 'Gold'
    elif stars >= 100:
        return 'Silver'
    else:
        return 'Bronze'

# ============================================
# TELEGRAM HANDLERS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user_id = update.effective_user.id
    student = get_student(user_id)
    
    message = f"""
🎓 *Welcome to Bina Bangsa P6 Tutor!*

Hi {student['name']}! I'm your personal tutor bot.

I can help you with:
- 📘 Math (Fractions, Ratio, Percentage, Algebra, Geometry)
- 🧪 Science (Photosynthesis, Ecosystems, Food Chain, etc)
- 📝 English (Grammar, Vocabulary, Comprehension)
- 🇮🇩 Bahasa Indonesia (Vocabulary, Grammar)
- 🇨🇳 Chinese/Mandarin (Characters, Vocabulary, Grammar)

*Commands:*
/help - Show all commands
/questions [topic] [count] - Get quiz questions
/score - Show your progress
/progress - Show progress by subject
/reset - Clear conversation
"""
    await update.message.reply_text(message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    message = """
*📚 Available Topics:*

**MATH:** fractions, ratio, percentage, algebra, geometry, data, time

**SCIENCE:** photosynthesis, ecosystems, food_chain, digestion, reproduction, weather, forces, machines, electricity

**ENGLISH:** grammar, vocabulary, comprehension, tenses, punctuation

**BAHASA INDONESIA:** vocabulary, grammar, stories, poetry, spelling

**CHINESE:** characters, vocabulary, grammar, radicals, listening

*Examples:*
/questions fractions 10
/questions ratio,fractions,algebra 20
/questions math 15
/questions 10 (random topic)

Or just chat normally, e.g:
"kasih aku 10 soal ratio sama pecahan"
"give me 20 science questions"

*Other Commands:*
/score - Your stars & level
/progress - Progress by subject
/reset - New conversation
"""
    await update.message.reply_text(message, parse_mode='Markdown')

async def questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send questions. Flexible: /questions [topic(s) or subject] [count]
    Topic(s) can be omitted (random topic), a single topic, a whole subject (e.g. 'math'),
    or several comma-separated topics/subjects (e.g. 'ratio,fractions,algebra')."""
    user_id = update.effective_user.id
    student = get_student(user_id)

    args = context.args or []

    count = 5
    topic_tokens = args
    if args and args[-1].isdigit():
        count = int(args[-1])
        topic_tokens = args[:-1]
    count = max(1, min(count, 50))

    raw_topics = ' '.join(topic_tokens).strip()
    if raw_topics:
        normalized = raw_topics.replace('+', ',').replace(' dan ', ',').replace(' and ', ',')
        spec_tokens = [t.strip().lower() for t in normalized.split(',') if t.strip()]
    else:
        spec_tokens = []

    topic_pairs = resolve_topics(spec_tokens)

    await update.message.reply_text(f"⏳ Generating {count} question(s)...")
    await send_quiz(update, student, topic_pairs, count)

async def submit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit answers and get score"""
    user_id = update.effective_user.id
    student = get_student(user_id)
    
    if 'current_questions' not in student:
        await update.message.reply_text("❌ No active quiz. Use /questions first!")
        return
    
    if not update.message.text.startswith('/submit'):
        # Parse answers from message
        answer_text = update.message.text
    else:
        await update.message.reply_text("Send your answers as: Q1: A, Q2: B, Q3: C, etc")
        return
    
    # Parse answers
    try:
        answers = {}
        for part in answer_text.split(','):
            q_num, answer = part.strip().split(':')
            q_num = int(q_num.replace('Q', '').strip())
            answers[q_num] = answer.strip().upper()
    except:
        await update.message.reply_text("❌ Invalid format. Use: Q1: A, Q2: B, Q3: C")
        return
    
    # Score quiz
    correct = 0
    total = len(student['current_questions'])
    feedback = "*📊 Your Answers:*\n\n"
    topic_stats = {}  # topic -> [correct_count, total_count], since a quiz can span several topics

    for i, q in enumerate(student['current_questions'], 1):
        correct_letter, correct_value = get_correct_answer_info(q)
        user_ans = answers.get(i, '❌').upper()
        is_correct = score_answer(user_ans, correct_letter)

        status = "✅" if is_correct else "❌"
        if is_correct:
            correct += 1

        feedback += f"{status} Q{i}: {user_ans} (Answer: {correct_letter} - {correct_value})\n"

        q_topic = q.get('_topic', student.get('current_topic', 'unknown'))
        stats = topic_stats.setdefault(q_topic, [0, 0])
        stats[1] += 1
        if is_correct:
            stats[0] += 1

    score_percent = (correct / total * 100) if total > 0 else 0
    stars_earned = calculate_stars(score_percent)

    student['stars'] += stars_earned
    student['level'] = update_level(student['stars'])

    # Update progress per topic actually covered in this quiz
    for q_topic, (t_correct, t_total) in topic_stats.items():
        t_score_percent = (t_correct / t_total * 100) if t_total > 0 else 0
        if q_topic not in student['progress']:
            student['progress'][q_topic] = {'attempts': 0, 'best': 0}
        student['progress'][q_topic]['attempts'] += 1
        student['progress'][q_topic]['best'] = max(student['progress'][q_topic]['best'], t_score_percent)
        student['progress'][q_topic]['last_score'] = t_score_percent

    feedback += f"\n*Score: {correct}/{total} ({score_percent:.0f}%)*"
    feedback += f"\n⭐ Stars Earned: +{stars_earned}"
    feedback += f"\n📊 Total Stars: {student['stars']}"
    feedback += f"\n🎖️ Level: {student['level']}"
    feedback += f"\n\n📈 [Lihat progress lengkap kamu di dashboard]({DASHBOARD_URL})"

    # Push to Firebase so the web dashboard can show it
    save_progress_to_firebase(user_id, student)

    await update.message.reply_text(feedback, parse_mode='Markdown')

async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show score and level"""
    user_id = update.effective_user.id
    student = get_student(user_id)
    
    message = f"""
*⭐ Your Progress*

👤 Student: {student['name']}
⭐ Stars: {student['stars']}
🎖️ Level: {student['level']}

*Level Requirements:*
🥉 Bronze: 0+ stars (current)
🥈 Silver: 100+ stars
🥇 Gold: 300+ stars
💎 Platinum: 500+ stars

📈 [Lihat progress lengkap kamu di dashboard]({DASHBOARD_URL})
"""
    await update.message.reply_text(message, parse_mode='Markdown')

async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show progress by subject"""
    user_id = update.effective_user.id
    student = get_student(user_id)
    
    if not student['progress']:
        await update.message.reply_text("No quizzes attempted yet. Use /questions to start!")
        return
    
    message = "*📊 Progress by Subject*\n\n"
    for topic, data in student['progress'].items():
        message += f"📘 {topic.title()}\n"
        message += f"  Attempts: {data['attempts']}\n"
        message += f"  Best: {data['best']:.0f}%\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation"""
    user_id = update.effective_user.id
    if user_id in student_data:
        student_data[user_id]['conversation_history'] = []
    await update.message.reply_text("✅ Conversation reset!")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle general messages"""
    user_id = update.effective_user.id
    student = get_student(user_id)
    text = update.message.text
    
    # Check if submitting answers
    if 'Q' in text and ':' in text and ',' in text:
        await submit_command(update, context)
        return

    # Check if this is a natural-language request for practice questions
    intent = detect_quiz_intent(text)
    if intent.get('is_quiz_request'):
        count = intent.get('count') or 5
        count = max(1, min(int(count), 50))
        topic_pairs = resolve_topics(intent.get('topics') or [])
        await update.message.reply_text(f"⏳ Generating {count} question(s)...")
        await send_quiz(update, student, topic_pairs, count)
        return

    # General chat with Claude
    student['conversation_history'].append({
        "role": "user",
        "content": text
    })
    
    response = anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system="You are a P6 tutor. Help the student learn Bina Bangsa curriculum. Be encouraging!",
        messages=student['conversation_history']
    )
    
    assistant_message = response.content[0].text
    student['conversation_history'].append({
        "role": "assistant",
        "content": assistant_message
    })
    
    await update.message.reply_text(assistant_message)

# ============================================
# MAIN
# ============================================

def main():
    """Start bot"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("questions", questions_command))
    app.add_handler(CommandHandler("submit", submit_command))
    app.add_handler(CommandHandler("score", score_command))
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("reset", reset_command))
    
    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("🚀 Bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()

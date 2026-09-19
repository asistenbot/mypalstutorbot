#!/usr/bin/env python3
"""
P6 Tutor Bot with Firebase Integration
Bina Bangsa School Curriculum + Chinese
Reads from Firebase database + Claude fallback
"""

import os
import json
import random
import re
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

def load_student_from_firebase(user_id):
    """Load a previously-saved student record from Firebase, if any."""
    if not FIREBASE_AVAILABLE:
        return None
    try:
        return db.reference(f'/students/{user_id}').get()
    except Exception as e:
        print(f"⚠️ Firebase read error: {e}")
        return None

def get_student(user_id):
    """Get (or lazily hydrate) a student's in-memory record.

    Bot restarts (redeploys, crashes, Railway restarts) wipe the in-memory
    student_data dict. Without this hydration step, a returning student's
    stars/progress would silently reset to 0 in memory, and their NEXT quiz
    submission would overwrite Firebase with that smaller total - quietly
    erasing real progress. So on first touch per process, we pull whatever
    was last saved in Firebase instead of assuming a blank slate.
    """
    if user_id not in student_data:
        saved = load_student_from_firebase(user_id)
        if saved:
            student_data[user_id] = {
                'name': saved.get('name', 'Student'),
                'stars': saved.get('stars', 0),
                'level': saved.get('level', 'Bronze'),
                'progress': saved.get('progress', {}) or {},
                'badges': saved.get('badges', []) or [],
                'conversation_history': []
            }
        else:
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

def strip_code_fence(text):
    """Strip a ```/```json code fence Claude sometimes wraps JSON output in.
    Handles both fenced-with-language and bare fences, whatever the exact
    marker length, instead of assuming a fixed offset."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening ``` or ```json line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        elif lines and lines[-1].strip().endswith("```"):
            lines[-1] = lines[-1].strip()[:-3]
        text = "\n".join(lines)
    return text.strip()

def generate_questions_claude(topic, count=5, language='english', qtype='ABCD'):
    """Generate questions using Claude API. qtype is 'ABCD' (multiple choice,
    default) or 'ESSAY' (open-ended, student writes their own answer)."""
    qtype = (qtype or 'ABCD').upper()
    if qtype not in ('ABCD', 'ESSAY'):
        qtype = 'ABCD'

    if qtype == 'ESSAY':
        type_instruction = "These must be OPEN-ENDED / ESSAY questions with NO multiple-choice options - the student writes a short answer (1-3 sentences) in their own words."
        schema = """[
  {
    "q": "Open-ended question text",
    "type": "ESSAY",
    "reasoning": "Brief notes on how you worked out what a correct answer should cover",
    "a": "A model/reference answer written in full sentences",
    "rubric": "2-4 short key points (as one string) an answer must mention to count as correct",
    "exp": "Short explanation for the student"
  }
]"""
        extra_check = ""
    else:
        type_instruction = "These must be multiple-choice (ABCD) questions with exactly 4 options each."
        schema = """[
  {
    "q": "Question text",
    "type": "ABCD",
    "options": ["first answer choice", "second answer choice", "third answer choice", "fourth answer choice"],
    "reasoning": "Brief step-by-step working showing exactly how you solved this",
    "a": "The correct option's exact text, copied verbatim character-for-character from one of the 4 items in options above (NOT a letter like A/B/C/D)",
    "exp": "Short explanation for the student"
  }
]"""
        extra_check = " After solving, re-read all 4 options and confirm exactly one matches your worked-out answer and the other 3 are genuinely wrong - this step is mandatory, mislabeling the correct option is the single most common mistake to avoid."

    prompt = f"""Generate {count} P6 Bina Bangsa School {topic.title()} quiz questions in {language}.

{type_instruction}

IMPORTANT: For each question, work out the correct answer STEP BY STEP first (put your working in the "reasoning" field) and double-check any arithmetic or facts before filling in "a", so "a" is guaranteed correct.{extra_check}

Format ONLY as a JSON array, no other text:
{schema}
"""

    try:
        response = anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = strip_code_fence(response.content[0].text.strip())
        questions = json.loads(text)
    except Exception as e:
        print(f"⚠️ Question generation error: {e}")
        return []

    # Validate before returning: never ship a question we can't reliably score.
    # For ABCD, 'a' must actually match one of the 4 options (or be a bare
    # letter) - if it doesn't match anything at all, drop the question rather
    # than silently sending something unscoreable.
    valid = []
    for q in questions if isinstance(questions, list) else []:
        if not isinstance(q, dict) or not q.get('q'):
            continue
        qt = str(q.get('type', qtype)).upper()
        if qt == 'ESSAY':
            if q.get('a'):
                q['type'] = 'ESSAY'
                valid.append(q)
            continue
        options = q.get('options', [])
        if not isinstance(options, list) or len(options) != 4:
            continue
        raw = str(q.get('a', '')).strip().upper()
        matches_option = any(str(opt).strip().upper() == raw for opt in options)
        matches_letter = raw in ('A', 'B', 'C', 'D')
        if matches_option or matches_letter:
            q['type'] = 'ABCD'
            valid.append(q)
    return valid

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
- type: "ESSAY" if the student asked for open-ended/essay/"esai"/written-answer questions, otherwise "ABCD" (default, multiple choice).

Respond with ONLY compact JSON, nothing else:
{{"is_quiz_request": true, "topics": ["ratio", "fractions"], "count": 10, "type": "ABCD"}}
or
{{"is_quiz_request": false, "topics": [], "count": 0, "type": "ABCD"}}
"""
    try:
        response = anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        out = strip_code_fence(response.content[0].text.strip())
        result = json.loads(out)
        if str(result.get('type', 'ABCD')).upper() not in ('ABCD', 'ESSAY'):
            result['type'] = 'ABCD'
        return result
    except Exception as e:
        print(f"Intent detection error: {e}")
        return {"is_quiz_request": False, "topics": [], "count": 0, "type": "ABCD"}

# ============================================
# QUESTION HANDLING
# ============================================

def format_question(question, index=1):
    """Format question for display"""
    q_text = question.get('q', '')
    options = question.get('options', [])
    qtype = str(question.get('type', 'ABCD')).upper()

    if qtype != 'ESSAY' and options and len(options) == 4:
        msg = f"*Question {index}:* {q_text}\n\n"
        msg += f"A) {options[0]}\n"
        msg += f"B) {options[1]}\n"
        msg += f"C) {options[2]}\n"
        msg += f"D) {options[3]}\n"
        return msg
    else:
        return f"*Question {index}:* {q_text}\n_(Write your answer in your own words)_\n"

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

def grade_essay_answers(items):
    """Grade a batch of essay answers in one Claude call.
    items: list of {index, q, a (model answer), rubric, user_answer}
    Returns {index: {'correct': bool, 'feedback': str}}"""
    if not items:
        return {}

    payload = [{
        "index": it['index'],
        "question": it['q'],
        "model_answer": it.get('a', ''),
        "rubric": it.get('rubric', ''),
        "student_answer": it.get('user_answer', '')
    } for it in items]

    prompt = f"""You are grading a P6 student's short written answers. For each item, compare the student's answer against the model answer and rubric. Be encouraging and lenient about wording, spelling and grammar - mark it correct if the core idea/substance is right even if phrased differently. A blank or clearly unrelated/off-topic answer is wrong.

Items (JSON):
{json.dumps(payload)}

Respond with ONLY a JSON array, no other text, one entry per item in the same order:
[
  {{"index": 1, "correct": true, "feedback": "One short encouraging sentence of feedback for the student"}}
]
"""
    try:
        response = anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = strip_code_fence(response.content[0].text.strip())
        results = json.loads(text)
        return {
            int(r['index']): {'correct': bool(r.get('correct')), 'feedback': str(r.get('feedback', ''))}
            for r in results if isinstance(r, dict) and 'index' in r
        }
    except Exception as e:
        print(f"⚠️ Essay grading error: {e}")
        # Fail safe: never silently mark as right or wrong when grading itself broke.
        return {it['index']: {'correct': False, 'feedback': '⚠️ Could not auto-grade this one, please double check with your tutor.'} for it in items}

async def send_quiz(update, student, topic_pairs, count, qtype='ABCD'):
    """Build a quiz across one or more (subject, topic) pairs, splitting count between them,
    using Firebase + adaptive difficulty where possible and falling back to Claude otherwise.
    qtype is 'ABCD' (default, multiple choice) or 'ESSAY' (open-ended)."""
    qtype = (qtype or 'ABCD').upper()
    if qtype not in ('ABCD', 'ESSAY'):
        qtype = 'ABCD'
    n = len(topic_pairs)
    counts = split_count(count, n)

    all_questions = []
    for (subject, topic), per_count in zip(topic_pairs, counts):
        if per_count <= 0:
            continue
        difficulty = get_next_difficulty(student, topic)
        # The Firebase question pool only contains multiple-choice questions,
        # so essay requests always go straight to Claude generation.
        qs = fetch_questions_from_firebase(topic, per_count, difficulty, subject) if (FIREBASE_AVAILABLE and qtype == 'ABCD') else None
        if not qs:
            qs = generate_questions_claude(topic, per_count, qtype=qtype)
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
    if qtype == 'ESSAY':
        current_msg += "\n_Send your answers as: Q1: <your answer>, Q2: <your answer>, etc - write in your own words_"
    else:
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
/questions fractions essay 5 (open-ended/essay questions)

Or just chat normally, e.g:
"kasih aku 10 soal ratio sama pecahan"
"give me 20 science questions"
"kasih aku 5 soal essay fractions"

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

    # Pull out an optional type keyword (essay/abcd) from the topic tokens
    qtype = 'ABCD'
    filtered_tokens = []
    for tok in topic_tokens:
        tl = tok.strip().lower()
        if tl in ('essay', 'esai', 'esei'):
            qtype = 'ESSAY'
        elif tl in ('abcd', 'mc', 'pg', 'pilihan', 'multiple', 'multiplechoice'):
            qtype = 'ABCD'
        else:
            filtered_tokens.append(tok)
    topic_tokens = filtered_tokens

    raw_topics = ' '.join(topic_tokens).strip()
    if raw_topics:
        normalized = raw_topics.replace('+', ',').replace(' dan ', ',').replace(' and ', ',')
        spec_tokens = [t.strip().lower() for t in normalized.split(',') if t.strip()]
    else:
        spec_tokens = []

    topic_pairs = resolve_topics(spec_tokens)

    await update.message.reply_text(f"⏳ Generating {count} question(s)...")
    await send_quiz(update, student, topic_pairs, count, qtype=qtype)

def parse_answers(text):
    """Parse 'Q1: B, Q2: some essay answer, could have commas, Q3: C' into
    {1: 'B', 2: 'some essay answer, could have commas', 3: 'C'}. Regex-based
    (not a naive split on ',') so essay answers containing commas don't get
    chopped up or thrown off the question numbering."""
    pattern = re.compile(r'Q\s*(\d+)\s*:\s*(.*?)(?=(?:,\s*)?Q\s*\d+\s*:|$)', re.S | re.I)
    answers = {}
    for m in pattern.finditer(text):
        num = int(m.group(1))
        ans = m.group(2).strip().rstrip(',').strip()
        answers[num] = ans
    return answers

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

    answers = parse_answers(answer_text)
    if not answers:
        await update.message.reply_text("❌ Invalid format. Use: Q1: A, Q2: B, Q3: C (or your written answer for essay questions)")
        return

    questions = student['current_questions']
    total = len(questions)

    lines = {}          # i -> display line
    correctness = {}    # i -> bool
    essay_items = []

    for i, q in enumerate(questions, 1):
        qtype = str(q.get('type', 'ABCD')).upper()
        user_ans = answers.get(i, '').strip()
        if qtype == 'ESSAY':
            essay_items.append({
                'index': i, 'q': q.get('q', ''), 'a': q.get('a', ''),
                'rubric': q.get('rubric', ''), 'user_answer': user_ans
            })
        else:
            correct_letter, correct_value = get_correct_answer_info(q)
            is_correct = bool(user_ans) and score_answer(user_ans, correct_letter)
            correctness[i] = is_correct
            status = "✅" if is_correct else "❌"
            shown = user_ans.upper() if user_ans else '(blank)'
            lines[i] = f"{status} Q{i}: {shown} (Answer: {correct_letter} - {correct_value})\n"

    if essay_items:
        essay_results = grade_essay_answers(essay_items)
        for item in essay_items:
            i = item['index']
            result = essay_results.get(i, {'correct': False, 'feedback': ''})
            is_correct = bool(result.get('correct'))
            correctness[i] = is_correct
            status = "✅" if is_correct else "❌"
            shown = item['user_answer'] if item['user_answer'] else '(blank)'
            fb = f" — {result['feedback']}" if result.get('feedback') else ""
            lines[i] = f"{status} Q{i}: {shown}{fb}\n"

    correct = sum(1 for v in correctness.values() if v)
    feedback = "*📊 Your Answers:*\n\n"
    topic_stats = {}  # topic -> [correct_count, total_count], since a quiz can span several topics

    for i, q in enumerate(questions, 1):
        feedback += lines.get(i, f"❓ Q{i}: (not answered)\n")
        q_topic = q.get('_topic', student.get('current_topic', 'unknown'))
        stats = topic_stats.setdefault(q_topic, [0, 0])
        stats[1] += 1
        if correctness.get(i):
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
    
    # Check if submitting answers (works for both "Q1: B, Q2: C" and a
    # single-question "Q1: B" with no comma, and for essay answers)
    if re.search(r'Q\s*\d+\s*:', text, re.I) and 'current_questions' in student:
        await submit_command(update, context)
        return

    # Check if this is a natural-language request for practice questions
    intent = detect_quiz_intent(text)
    if intent.get('is_quiz_request'):
        count = intent.get('count') or 5
        # A bare trailing number in the message (e.g. "soal ratio 2") is a much
        # more reliable count signal than the AI's own extraction, which can
        # misread that pattern and fall back to its "default to 5" instruction.
        # Trust the explicit number when there is one.
        tokens = text.strip().split()
        if tokens and tokens[-1].isdigit():
            count = int(tokens[-1])
        count = max(1, min(int(count), 50))
        qtype = str(intent.get('type', 'ABCD') or 'ABCD').upper()
        if qtype not in ('ABCD', 'ESSAY'):
            qtype = 'ABCD'
        topic_pairs = resolve_topics(intent.get('topics') or [])
        await update.message.reply_text(f"⏳ Generating {count} question(s)...")
        await send_quiz(update, student, topic_pairs, count, qtype=qtype)
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

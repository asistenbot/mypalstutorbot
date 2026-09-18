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
# FIREBASE FUNCTIONS
# ============================================

def get_firebase_questions(topic):
    """Fetch questions from Firebase"""
    if not FIREBASE_AVAILABLE:
        return None
    
    try:
        # Parse topic: "fractions" -> math/fractions
        subject, subtopic = topic.lower().split('_') if '_' in topic else (topic.lower(), topic.lower())
        
        path = f'/questions/{subject}/{subtopic}'
        ref = db.reference(path)
        data = ref.get()
        
        if data:
            return data
    except Exception as e:
        print(f"Firebase error: {e}")
    
    return None

def fetch_questions_from_firebase(topic, count=5, difficulty='mixed'):
    """Get questions from Firebase with fallback"""
    firebase_data = get_firebase_questions(topic)
    
    if not firebase_data:
        return None
    
    questions = []
    
    # Get difficulty levels
    if difficulty == 'mixed':
        for level in ['easy', 'medium', 'hard']:
            if level in firebase_data:
                level_questions = list(firebase_data[level].values()) if isinstance(firebase_data[level], dict) else firebase_data[level]
                questions.extend(level_questions[:count//3 + 1])
    else:
        if difficulty in firebase_data:
            level_questions = list(firebase_data[difficulty].values()) if isinstance(firebase_data[difficulty], dict) else firebase_data[difficulty]
            questions.extend(level_questions)
    
    return random.sample(questions, min(count, len(questions)))

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
        "a": "Correct answer",
        "type": "ABCD",
        "options": ["A", "B", "C", "D"],
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
/questions grammar 5
/questions characters 8 chinese

*Other Commands:*
/score - Your stars & level
/progress - Progress by subject
/reset - New conversation
"""
    await update.message.reply_text(message, parse_mode='Markdown')

async def questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send questions"""
    user_id = update.effective_user.id
    student = get_student(user_id)
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /questions [topic] [count]\nExample: /questions fractions 10")
        return
    
    topic = context.args[0].lower()
    count = int(context.args[1]) if len(context.args) > 1 else 5
    count = min(count, 20)  # Max 20 questions
    
    await update.message.reply_text(f"⏳ Generating {count} {topic} questions...")
    
    # Try Firebase first
    questions = fetch_questions_from_firebase(topic, count) if FIREBASE_AVAILABLE else None
    
    # Fallback to Claude
    if not questions:
        questions = generate_questions_claude(topic, count)
    
    if not questions:
        await update.message.reply_text("❌ Could not generate questions. Try another topic.")
        return
    
    # Store for scoring
    student['current_questions'] = questions
    student['current_topic'] = topic
    student['answers'] = []
    
    # Send questions
    msg = f"*{topic.upper()} QUIZ - {len(questions)} Questions*\n\n"
    for i, q in enumerate(questions, 1):
        msg += format_question(q, i) + "\n"
    
    msg += "\n_Send answers as: Q1: A, Q2: B, Q3: C, etc_"
    await update.message.reply_text(msg, parse_mode='Markdown')

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
    
    for i, q in enumerate(student['current_questions'], 1):
        correct_ans = q.get('a', '').upper()
        user_ans = answers.get(i, '❌').upper()
        is_correct = score_answer(user_ans, correct_ans)
        
        status = "✅" if is_correct else "❌"
        if is_correct:
            correct += 1
        
        feedback += f"{status} Q{i}: {user_ans} (Answer: {correct_ans})\n"
    
    score_percent = (correct / total * 100) if total > 0 else 0
    stars_earned = calculate_stars(score_percent)
    
    student['stars'] += stars_earned
    student['level'] = update_level(student['stars'])
    
    # Update progress
    topic = student.get('current_topic', 'unknown')
    if topic not in student['progress']:
        student['progress'][topic] = {'attempts': 0, 'best': 0}
    student['progress'][topic]['attempts'] += 1
    student['progress'][topic]['best'] = max(student['progress'][topic]['best'], score_percent)
    
    feedback += f"\n*Score: {correct}/{total} ({score_percent:.0f}%)*"
    feedback += f"\n⭐ Stars Earned: +{stars_earned}"
    feedback += f"\n📊 Total Stars: {student['stars']}"
    feedback += f"\n🎖️ Level: {student['level']}"
    
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

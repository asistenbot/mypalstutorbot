#!/usr/bin/env python3
"""
My Pals Tutor Bot - Firebase Edition
Telegram bot untuk P6 Singapore Curriculum dengan Firebase database
"""

import os
import json
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from anthropic import Anthropic
import firebase_admin
from firebase_admin import credentials, db

# ============================================
# INITIALIZE FIREBASE
# ============================================
try:
    cred = credentials.Certificate('firebase-credentials.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://mypalstutorbot-default-rtdb.asia-southeast1.firebasedatabase.app'
    })
    FIREBASE_ENABLED = True
    print("✅ Firebase connected")
except Exception as e:
    print(f"⚠️ Firebase error: {e}")
    FIREBASE_ENABLED = False

# ============================================
# ANTHROPIC CLIENT
# ============================================
client = Anthropic()
user_convos = {}

SYSTEM_PROMPT = """You are a friendly P6 tutor using My Pals Are Here 3rd Edition textbook.

ALWAYS answer in ENGLISH, even if student asks in Indonesian.

Topics: Math, Science, English, Bahasa Indonesia (P6 level)

WHEN ASKED FOR QUESTIONS:
- Generate exact number requested (20, 15, 5, etc)
- Format: 15 ABCD questions + 5 essay questions (unless specified)
- Each question has: question, options (A/B/C/D), answer, explanation
- Include difficulty: Easy/Medium/Hard
- Include tricks/mnemonics

WHEN EXPLAINING:
- Use analogies and real-world examples
- Include memory tricks
- Step-by-step breakdown
- Emojis to make fun

When asked for questions, provide in this format:
Q1. [Question text]
A) Option
B) Option
C) Option
D) Option
Answer: [Letter]
Explanation: [Why this is correct]

ESSAY questions:
EQ1. [Question text]
Sample answer: [Guide]

BE FLEXIBLE: Student can ask for:
- "5 questions about fractions"
- "10 ABCD only about ratio"
- "3 easy + 2 medium about photosynthesis"
- Etc - adapt to their request"""

# ============================================
# FIREBASE FUNCTIONS
# ============================================
def get_questions(subject, topic, difficulty, count=20):
    """Get questions from Firebase"""
    try:
        path = f'/questions/{subject}/{topic}/{difficulty}'
        ref = db.reference(path)
        data = ref.get()
        
        if not data:
            return None
        
        # Randomly select 'count' questions
        all_qs = list(data.values())
        selected = random.sample(all_qs, min(count, len(all_qs)))
        return selected
    except:
        return None

def save_score(user_id, subject, topic, score, max_score):
    """Save quiz score to Firebase"""
    try:
        timestamp = datetime.now().isoformat()
        path = f'/users/{user_id}/scores/{subject}_{topic}'
        ref = db.reference(path)
        
        score_data = {
            'score': score,
            'max': max_score,
            'percentage': (score/max_score)*100,
            'timestamp': timestamp,
            'stars': int((score/max_score)*15)  # Max 15 stars
        }
        
        ref.push(score_data)
        return score_data['stars']
    except:
        return 0

def add_stars(user_id, stars):
    """Add stars to user profile"""
    try:
        path = f'/users/{user_id}/stars'
        ref = db.reference(path)
        current = ref.get() or 0
        ref.set(current + stars)
        return current + stars
    except:
        return 0

# ============================================
# BOT HANDLERS
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_convos[user_id] = []
    
    msg = """Hello! I'm your My Pals Tutor Bot! 👋

I help with:
📚 Mathematics | 🔬 Science | 🇬🇧 English | 🇮🇩 Bahasa Indonesia

Ask me anything:
- "Explain fractions for P6"
- "Give me 20 questions about photosynthesis"
- "5 medium questions: 4 ABCD + 1 essay about grammar"
- "Jelaskan bilangan bulat" (I'll reply in English!)

Commands:
/help - Show this message
/reset - Start new topic
/score - View your score
/badges - View achievements"""
    
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_convos[user_id] = []
    await update.message.reply_text("✅ Conversation reset! Ask me a new topic.")

async def score_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        if FIREBASE_ENABLED:
            stars_ref = db.reference(f'/users/{user_id}/stars')
            stars = stars_ref.get() or 0
            
            level = "Bronze"
            if stars >= 300:
                level = "Platinum"
            elif stars >= 100:
                level = "Gold"
            elif stars >= 50:
                level = "Silver"
            
            msg = f"⭐ Your Score\n\nStars: {stars}\nLevel: {level}"
        else:
            msg = "Firebase offline - score tracking unavailable"
    except:
        msg = "Could not fetch score"
    
    await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    
    if user_id not in user_convos:
        user_convos[user_id] = []
    
    user_convos[user_id].append({"role": "user", "content": user_message})
    await update.message.chat.send_action("typing")
    
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=user_convos[user_id]
        )
        
        reply = response.content[0].text
        user_convos[user_id].append({"role": "assistant", "content": reply})
        
        # Split if too long for Telegram (4096 char limit)
        if len(reply) > 4090:
            for chunk in [reply[i:i+4090] for i in range(0, len(reply), 4090)]:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(reply)
            
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def main():
    """Start the bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return
    
    app = Application.builder().token(token).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("score", score_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot started!")
    await app.run_polling(allowed_updates=update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())

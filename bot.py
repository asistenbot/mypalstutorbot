#!/usr/bin/env python3
"""
My Pals Tutor Bot - dengan Score & Rewards
Track stars, levels, badges per topic
"""

import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch
import io

client = Anthropic()
user_convos = {}

# In-memory user database (akan di-upgrade ke Firebase nanti)
user_stats = {}

SYSTEM_PROMPT = """You are a friendly P6 tutor using My Pals Are Here 3rd Edition textbook.

ALWAYS answer in ENGLISH, even if student asks in Indonesian.

Topics: Math, Science, English, Bahasa Indonesia (P6 level)

WHEN ASKED FOR QUESTIONS:
- Generate exact number requested
- Format: 15 ABCD questions + 5 essay questions (unless specified)
- IMPORTANT: Do NOT include answers in the questions themselves
- Each question should be clear and standalone
- Include difficulty level (Easy/Medium/Hard)

WHEN EXPLAINING:
- Use analogies and real-world examples
- Include memory tricks
- Step-by-step breakdown
- Use emojis to make it fun

BE FLEXIBLE: Student can ask for any number/format of questions."""

# Reward thresholds
LEVELS = {
    "Bronze": 0,
    "Silver": 100,
    "Gold": 300,
    "Platinum": 500
}

def get_level(stars):
    """Get level based on stars"""
    if stars >= 500:
        return "Platinum"
    elif stars >= 300:
        return "Gold"
    elif stars >= 100:
        return "Silver"
    else:
        return "Bronze"

def init_user(user_id):
    """Initialize user stats"""
    if user_id not in user_stats:
        user_stats[user_id] = {
            "name": f"Student_{user_id}",
            "stars": 0,
            "level": "Bronze",
            "topics": {},
            "created": datetime.now().isoformat()
        }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_convos[user_id] = []
    init_user(user_id)
    
    msg = """Hello! I'm your My Pals Tutor Bot! 👋

I help with:
📚 Mathematics | 🔬 Science | 🇬🇧 English | 🇮🇩 Bahasa Indonesia

Ask me anything:
- "Explain fractions for P6"
- "Give me 20 questions about photosynthesis"
- "5 medium questions: 4 ABCD + 1 essay about grammar"

Commands:
/help - Show this message
/reset - Start new topic
/questions [topic] [count] - Get questions with answer sheet PDF
/score - View your stars & level
/progress - View progress by topic
/submit - Submit quiz answers for scoring"""
    
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_convos[user_id] = []
    await update.message.reply_text("✅ Conversation reset! Ask me a new topic.")

async def score_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user score, stars, and level"""
    user_id = update.effective_user.id
    init_user(user_id)
    
    stats = user_stats[user_id]
    level = stats["level"]
    stars = stats["stars"]
    
    # Get next level milestone
    level_list = list(LEVELS.items())
    current_idx = [i for i, (l, _) in enumerate(level_list) if l == level][0]
    if current_idx < len(level_list) - 1:
        next_level = level_list[current_idx + 1]
        needed_stars = next_level[1] - stars
        progress = f"\n📈 {needed_stars} more stars to reach {next_level[0]}!"
    else:
        progress = "\n🏆 You've reached the highest level!"
    
    msg = f"""⭐ YOUR SCORE

Stars: {stars}
Level: {level}
{progress}

Topics Completed: {len([t for t in stats['topics'] if stats['topics'][t]['completed'] > 0])}"""
    
    await update.message.reply_text(msg)

async def progress_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show progress by topic"""
    user_id = update.effective_user.id
    init_user(user_id)
    
    stats = user_stats[user_id]
    
    if not stats['topics']:
        msg = "No progress yet! Try /questions [topic] to start."
    else:
        msg = "📊 PROGRESS BY TOPIC\n\n"
        for topic, data in stats['topics'].items():
            completed = data.get('completed', 0)
            total = data.get('total', 0)
            score = data.get('score', 0)
            msg += f"{topic}: {completed}/{total} completed | Score: {score}%\n"
    
    await update.message.reply_text(msg)

async def submit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide for submitting answers"""
    msg = """📝 HOW TO SUBMIT ANSWERS:

1. Download the answer sheet PDF
2. Do the questions on paper or file
3. Reply with your answers in this format:

Q1: B
Q2: A
Q3: C
EQ1: [Your essay answer]

I'll score and give you stars! ⭐"""
    
    await update.message.reply_text(msg)

async def score_answers(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str = "General"):
    """Score submitted answers"""
    user_id = update.effective_user.id
    user_message = update.message.text
    init_user(user_id)
    
    try:
        # Use Claude to score answers
        score_prompt = f"""Score these answers for a P6 {topic} quiz. Be generous but fair.

Answers:
{user_message}

Reply with:
1. Total score (as percentage)
2. Brief feedback per answer
3. Overall comment

Format:
Score: XX%
Feedback:
[Your feedback]"""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": score_prompt}]
        )
        
        feedback = response.content[0].text
        
        # Extract score (simple parsing)
        score_line = [l for l in feedback.split('\n') if 'Score:' in l]
        if score_line:
            try:
                score_pct = int(score_line[0].split(':')[1].strip().replace('%', ''))
            except:
                score_pct = 75  # Default
        else:
            score_pct = 75
        
        # Calculate stars (max 15 per quiz)
        stars_earned = int((score_pct / 100) * 15)
        
        # Update stats
        if topic not in user_stats[user_id]['topics']:
            user_stats[user_id]['topics'][topic] = {
                'completed': 0,
                'total': 0,
                'score': 0,
                'stars': 0
            }
        
        user_stats[user_id]['topics'][topic]['completed'] += 1
        user_stats[user_id]['topics'][topic]['score'] = score_pct
        user_stats[user_id]['topics'][topic]['stars'] += stars_earned
        user_stats[user_id]['stars'] += stars_earned
        user_stats[user_id]['level'] = get_level(user_stats[user_id]['stars'])
        
        msg = f"""✅ SCORED!

Score: {score_pct}%
Stars Earned: +{stars_earned} ⭐
Total Stars: {user_stats[user_id]['stars']}
Level: {user_stats[user_id]['level']}

{feedback}"""
        
        await update.message.reply_text(msg)
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error scoring: {str(e)}")

async def questions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate questions and answer sheet"""
    user_id = update.effective_user.id
    init_user(user_id)
    
    if not context.args:
        await update.message.reply_text("Usage: /questions [topic] [count]\nExample: /questions fractions 10")
        return
    
    topic = context.args[0]
    count = int(context.args[1]) if len(context.args) > 1 else 20
    
    await update.message.chat.send_action("typing")
    
    try:
        # Request questions from Claude
        prompt = f"""Generate {count} P6-level questions about {topic}.

Format EXACTLY like this (NO ANSWERS IN QUESTIONS):

Q1. [Question text]
A) Option A
B) Option B  
C) Option C
D) Option D

For essay questions use:
EQ1. [Essay question text]

Do NOT include answers or explanations in the questions section."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        questions_text = response.content[0].text
        
        # Send questions
        if len(questions_text) > 4090:
            for chunk in [questions_text[i:i+4090] for i in range(0, len(questions_text), 4090)]:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(questions_text)
        
        # Request answer key
        await update.message.chat.send_action("typing")
        
        answer_prompt = f"""Based on the {topic} questions just provided, give ONLY the answer key with brief explanations.

Format:
Q1. Answer: [Letter]
Explanation: [Brief]

EQ1. Sample Answer: [Guide]"""

        answer_response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": questions_text},
                {"role": "user", "content": answer_prompt}
            ]
        )
        
        answers_text = answer_response.content[0].text
        
        # Generate PDF
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        
        story = []
        story.append(Paragraph(f"📝 {topic.title()} - Answer Key", styles['Heading1']))
        story.append(Paragraph(f"P6 | {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        for line in answers_text.split('\n'):
            if line.strip():
                story.append(Paragraph(line, styles['Normal']))
                story.append(Spacer(1, 0.05*inch))
        
        doc.build(story)
        pdf_buffer.seek(0)
        
        # Send PDF
        await update.message.reply_document(
            document=pdf_buffer,
            filename=f"{topic}_answers.pdf",
            caption="📄 Answer Sheet\n\nWhen done, reply with your answers to get scored!"
        )
        
        # Track in progress
        if topic not in user_stats[user_id]['topics']:
            user_stats[user_id]['topics'][topic] = {
                'completed': 0,
                'total': count,
                'score': 0,
                'stars': 0
            }
        else:
            user_stats[user_id]['topics'][topic]['total'] = count
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    
    init_user(user_id)
    
    if user_id not in user_convos:
        user_convos[user_id] = []
    
    # Check if looks like answer submission
    if any(marker in user_message.lower() for marker in ['q1:', 'q1.', 'eq1:', 'answer:']):
        # Likely answer submission
        await score_answers(update, context, topic="Quiz")
        return
    
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
        
        if len(reply) > 4090:
            for chunk in [reply[i:i+4090] for i in range(0, len(reply), 4090)]:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(reply)
            
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

def main():
    """Start the bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return
    
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("questions", questions_cmd))
    app.add_handler(CommandHandler("score", score_cmd))
    app.add_handler(CommandHandler("progress", progress_cmd))
    app.add_handler(CommandHandler("submit", submit_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot started with Score & Rewards!")
    app.run_polling()

if __name__ == '__main__':
    main()

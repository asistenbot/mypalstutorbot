#!/usr/bin/env python3
"""
My Pals Tutor Bot - dengan PDF Answer Sheet
Questions & Answers terpisah
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

BE FLEXIBLE: Student can ask for:
- "5 questions about fractions"
- "10 ABCD only about ratio"
- "3 easy + 2 medium about photosynthesis"
"""

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
/questions [topic] [count] - Get questions with answer sheet PDF"""
    
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_convos[user_id] = []
    await update.message.reply_text("✅ Conversation reset! Ask me a new topic.")

async def questions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate questions and answer sheet"""
    user_id = update.effective_user.id
    
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

Q2. [Next question]
...

For essay questions use:
EQ1. [Essay question text]

Do NOT include answers or explanations in the questions section.
Make questions clear and standalone."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        questions_text = response.content[0].text
        
        # Send questions to chat
        if len(questions_text) > 4090:
            for chunk in [questions_text[i:i+4090] for i in range(0, len(questions_text), 4090)]:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(questions_text)
        
        # Request answer key from Claude
        await update.message.chat.send_action("typing")
        
        answer_prompt = f"""Based on the questions you just gave about {topic}, provide ONLY the answer key with brief explanations.

Format:

Q1. Answer: [Letter]
Explanation: [Brief explanation]

Q2. Answer: [Letter]
Explanation: [Brief explanation]

For essay questions:
EQ1. Sample Answer: [Guide/Sample answer]

Be concise but clear."""

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
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor='#1f4788',
            spaceAfter=12,
            alignment=1
        )
        
        story = []
        story.append(Paragraph(f"📝 {topic.title()} - Answer Key", title_style))
        story.append(Paragraph(f"P6 Level | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Add answers to PDF
        for line in answers_text.split('\n'):
            if line.strip():
                if line.startswith('Q') or line.startswith('EQ'):
                    story.append(Paragraph(line, styles['Heading3']))
                else:
                    story.append(Paragraph(line, styles['Normal']))
                story.append(Spacer(1, 0.1*inch))
        
        doc.build(story)
        pdf_buffer.seek(0)
        
        # Send PDF
        await update.message.reply_document(
            document=pdf_buffer,
            filename=f"{topic}_answers.pdf",
            caption="📄 Answer Sheet - Keep separate from questions!"
        )
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

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
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("questions", questions_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot started with PDF support!")
    app.run_polling()

if __name__ == '__main__':
    main()

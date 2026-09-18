#!/usr/bin/env python3
"""
My Pals Tutor Bot - Blocking Version (Stable)
Telegram bot untuk P6 Singapore Curriculum
"""

import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic

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

BE FLEXIBLE: Student can ask for:
- "5 questions about fractions"
- "10 ABCD only about ratio"
- "3 easy + 2 medium about photosynthesis"
- Etc - adapt to their request"""

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
/reset - Start new topic"""
    
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_convos[user_id] = []
    await update.message.reply_text("✅ Conversation reset! Ask me a new topic.")

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

def main():
    """Start the bot - BLOCKING VERSION"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return
    
    app = Application.builder().token(token).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot started (blocking mode)!")
    app.run_polling()

if __name__ == '__main__':
    main()

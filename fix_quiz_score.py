#!/usr/bin/env python3
"""One-off script: manually credit the 15-question Fractions+Ratio quiz
(sent 18 Sept, answered 19:35 WIB) that never got scored/saved correctly
due to the answer-format bug (fixed in bot.py) and a stuck-bot Firebase
write failure. Run this ONCE in Railway's Shell, then delete/ignore it.

Corrected result (manually verified against the actual quiz screenshots):
  Fractions: 7/8 correct (87.5%)
  Ratio:     7/7 correct (100%)   [Q13 counted correct - user typed the
                                    answer's value "4" instead of its
                                    letter "B", clearly the intended answer]
  Overall:   14/15 (93%) -> +15 stars
"""
import firebase_admin
from firebase_admin import credentials, db
import json
import os

USER_ID = "2025794087"

try:
    firebase_creds_env = os.getenv('FIREBASE_CREDENTIALS_JSON')
    if firebase_creds_env:
        cred = credentials.Certificate(json.loads(firebase_creds_env))
    else:
        cred = credentials.Certificate('firebase-credentials.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://mypalstutorbot-default-rtdb.asia-southeast1.firebasedatabase.app'
    })
    print("Firebase connected")
except Exception as e:
    print(f"Firebase error: {e}")
    raise SystemExit(1)

ref = db.reference(f'/students/{USER_ID}')
student = ref.get() or {}
print("Current state:", json.dumps(student, indent=2))

progress = student.get('progress', {})

def apply_topic(topic, score_percent):
    t = progress.get(topic, {'attempts': 0, 'best': 0})
    t['attempts'] = t.get('attempts', 0) + 1
    t['best'] = max(t.get('best', 0), score_percent)
    t['last_score'] = score_percent
    progress[topic] = t

apply_topic('fractions', 87.5)   # 7/8 correct
apply_topic('ratio', 100.0)      # 7/7 correct

stars_earned = 15  # overall 14/15 = 93% -> >=90% bracket
student['stars'] = student.get('stars', 0) + stars_earned
student['progress'] = progress
student['name'] = student.get('name', 'Student')

# Mirror update_level() from bot.py
stars = student['stars']
if stars >= 500:
    student['level'] = 'Platinum'
elif stars >= 300:
    student['level'] = 'Gold'
elif stars >= 100:
    student['level'] = 'Silver'
else:
    student['level'] = 'Bronze'

ref.set(student)
print("\nUpdated state:", json.dumps(student, indent=2))
print(f"\nDone. +{stars_earned} stars applied. New total: {student['stars']} ({student['level']})")

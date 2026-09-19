#!/usr/bin/env python3
"""One-off script: reset this student's stars/level/progress back to a clean
slate (0 stars, Bronze, no progress history) after the grading/generation
bug fixes were deployed. Run this ONCE in Railway's Console, AFTER the new
bot.py has already been redeployed and is live - not before - so the bot
doesn't hydrate stale (pre-reset) numbers back into memory before Firebase
gets zeroed out."""
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
print("Current state (before reset):", json.dumps(student, indent=2))

reset_state = {
    'name': student.get('name', 'Student'),
    'stars': 0,
    'level': 'Bronze',
    'progress': {},
    'badges': [],
}

ref.set(reset_state)
print("\nReset done. New state:", json.dumps(reset_state, indent=2))

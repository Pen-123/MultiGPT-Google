import os
import asyncio
import re
import urllib.parse
import aiohttp
import time
import random
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import calendar
from flask import Flask, request, jsonify
from threading import Thread

# ------------------------------
# Flask Setup for Google Chat
# ------------------------------
app = Flask(__name__)

# ------------------------------
# Logging Setup
# ------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('MultiGPT')

# ------------------------------
# Configuration (Inherited from your original)
# ------------------------------
GROQ_API_KEYS = [key for key in [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY2")] if key]
HF_TOKENS = [t for t in [os.getenv("HF_TOKEN"), os.getenv("HF_TOKEN2")] if t]
IMGBB_API_KEY = os.getenv("HF_IMAGES")
SILICONFLOW_API_KEYS = []
idx = 0
while True:
    key = os.getenv(f"SILICONFLOW_API_KEY{'' if idx == 0 else idx+1}")
    if key:
        SILICONFLOW_API_KEYS.append(key)
        idx += 1
    else:
        break

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
TZ_UAE = ZoneInfo("Asia/Dubai")

# ------------------------------
# Bot Logic Class (Your Core)
# ------------------------------
class BotCore:
    def __init__(self):
        self.current_mode = "chill"
        self.current_llm = "openai/gpt-oss-20b"
        self.groq_key_index = 0
        self.hf_key_index = 0
        self.siliconflow_key_index = 0
        self.memory_enabled = False
        self.saved_memory = []
        self.video_jobs = {} # Tracking status for Google Chat
        
        # Load Pen Archive
        self.pen_archive = self.load_pen_archive()
        
        # Modes (Sanitized for Safety Guidelines)
        self.mode_prompts = {
            "chill": "You are MultiGPT. Be a mission operative on Google Chat. Use bold and italics. Stay chill.",
            "unhinged": "You are MultiGPT in 'Chaos Mode'. Be intense, dramatic, and use extreme internet slang. (Note: Remain within safety guidelines).",
            "coder": "You are MultiGPT, an expert AI programmer. Provide clean code blocks.",
            "childish": "You are MultiGPT. Act immature, use words like 'skibidi' and 'gyatt' constantly."
        }

    def load_pen_archive(self):
        url = "https://raw.githubusercontent.com/Pen-123/upd-multigpt/refs/heads/main/archives.txt"
        try:
            import requests
            r = requests.get(url, timeout=5)
            return r.text if r.status_code == 200 else ""
        except: return ""

    async def ai_call(self, prompt):
        # API Key Rotation Logic
        current_key = GROQ_API_KEYS[self.groq_key_index % len(GROQ_API_KEYS)]
        system_content = f"Today: {datetime.now(TZ_UAE)}. {self.mode_prompts.get(self.current_mode)}\n{self.pen_archive}"
        
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": system_content}, {"role": "user", "content": prompt}]
        }
        headers = {"Authorization": f"Bearer {current_key}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_API_URL, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                return f"❌ Error: {resp.status}"

    async def generate_image(self, prompt):
        # Pollinations fallback as it's the most reliable for webhooks
        url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
        return url # Return URL for Google Chat to display

# Initialize Core
bot = BotCore()

# ------------------------------
# Google Chat Routes
# ------------------------------
@app.route('/google_chat', methods=['POST'])
def google_chat():
    event = request.get_json()
    etype = event.get('type')

    # 1. URL Verification
    if etype == 'ADDED_TO_SPACE':
        return jsonify({"text": "⚡ **MultiGPT IS ONLINE.** All systems (Image/Video/AI) operational."})

    # 2. Handle Messages
    if etype == 'MESSAGE':
        text = event['message'].get('text', '').strip()
        user_id = event['user']['name']

        # Command: /mode
        if text.startswith('/mode'):
            mode = text.replace('/mode', '').strip()
            if mode in bot.mode_prompts:
                bot.current_mode = mode
                return jsonify({"text": f"✅ Mode switched to **{mode}**"})
            return jsonify({"text": "Available modes: chill, unhinged, coder, childish"})

        # Command: /image
        if text.startswith('/image'):
            prompt = text.replace('/image', '').strip()
            img_url = asyncio.run(bot.generate_image(prompt))
            return jsonify({
                "cardsV2": [{
                    "cardId": "imageCard",
                    "card": {
                        "header": {"title": "MultiGPT Image Gen", "subtitle": prompt},
                        "sections": [{"widgets": [{"image": {"imageUrl": img_url}}]}]
                    }
                }]
            })

        # Default AI Response
        reply = asyncio.run(bot.ai_call(text))
        return jsonify({"text": reply})

    return jsonify({"text": "Event processed."})

@app.route('/')
def health():
    return "MultiGPT Core Active", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

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
from typing import Optional, Dict, List, Tuple

from aiohttp import web

# ------------------------------
# Logging Setup
# ------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MultiGPT')

# ------------------------------
# Configuration
# ------------------------------
GROQ_API_KEYS = [
    key for key in [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY2")]
    if key
]
if not GROQ_API_KEYS:
    raise ValueError("No GROQ_API_KEY environment variables set!")

HF_TOKENS = [
    t for t in [os.getenv("HF_TOKEN"), os.getenv("HF_TOKEN2")]
    if t
]

SILICONFLOW_API_KEYS = []
idx = 0
while True:
    key = os.getenv(f"SILICONFLOW_API_KEY{'' if idx == 0 else idx+1}")
    if key:
        SILICONFLOW_API_KEYS.append(key)
        idx += 1
    else:
        break
if not SILICONFLOW_API_KEYS:
    logger.warning("No SILICONFLOW_API_KEY environment variables set! Video generation will fail.")

IMGBB_API_KEY = os.getenv("HF_IMAGES")
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY") or "sk_e9Gh0E5vQH0UQUhiZ9gRdJCmTYspFtB9"

OPENROUTER_API_KEY = "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"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Constants
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
POLLINATIONS_AUDIO_URL = "https://gen.pollinations.ai/audio"
MAX_SAVED = 5
MAX_MEMORY = 50
TZ_UAE = ZoneInfo("Asia/Dubai")
USER_COOLDOWN_SECONDS = 5
COOLDOWN_DURATION = 40


# ------------------------------
# Helper Functions
# ------------------------------
def format_countdown_to_dec19(now: datetime) -> str:
    def add_months(dt: datetime, months: int) -> datetime:
        year = dt.year + (dt.month - 1 + months) // 12
        month = (dt.month - 1 + months) % 12 + 1
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)
    
    target = datetime(now.year, 12, 19, 0, 0, 0, tzinfo=now.tzinfo)
    if target <= now:
        target = datetime(now.year + 1, 12, 19, 0, 0, 0, tzinfo=now.tzinfo)
    
    months = 0
    while True:
        next_month_date = add_months(now, months + 1)
        if next_month_date <= target:
            months += 1
        else:
            break
    
    after_months = add_months(now, months)
    delta = target - after_months
    total_seconds = int(delta.total_seconds())
    days = delta.days
    weeks = days // 7
    days_remaining = days % 7
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    parts = []
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if weeks:
        parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
    if days_remaining:
        parts.append(f"{days_remaining} day{'s' if days_remaining != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds or not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    return ", ".join(parts)


# ------------------------------
# Bot Core System
# ------------------------------
class BotCore:
    def __init__(self):
        # State variables
        self.ping_only = True
        self.saved_chats: Dict[str, List[Tuple[str, str]]] = {}
        self.current_chat: Optional[str] = None
        self.memory_enabled = False
        self.saved_memory: List[Tuple[str, str]] = []
        self.current_mode = "chill"
        self.current_quality_mode = "smart"
        self.current_image_mode = "smart"
        self.current_llm = "openai/gpt-oss-20b"
        self.current_model_list = ["openai/gpt-oss-20b"]
        self.current_model_index = 0
        self.current_hf_model = "black-forest-labs/FLUX.1-schnell"
        
        # API key rotation
        self.groq_key_index = 0
        self.hf_key_index = 0
        self.siliconflow_key_index = 0
        self.last_key_rotation = 0
        self.model_cooldowns = {}
        
        # Job tracking
        self.video_jobs = {}
        self.music_jobs = {}
        self.annoying_channels = set()
        self.pending_annoying_messages = {}
        self.user_cooldowns = {}
        
        # Load pen archive
        self.pen_archive = self.load_pen_archive()
        
        # Mode prompts
        self.mode_prompts = {
            "chill": (
                "You are MultiGPT - be as dumb as possible and act like you're a mission operative this is discord syntax ALSO, dont ALways use discord syntax, use it when its necessary. **Bold text**: **Yo, this is bold!**\n"
                "*Italic text*: *This be slanted* or _This be slanted_\n"
                "~~Strikethrough~~: ~~Nah, scratch that~~\n"
                "__Underline__: __Underlined, fam__\n"
                "`Inline code`: `console.log(\"Lit code\")`\n"
                "```Code block```\n"
                "```javascript\n"
                "console.log(\"Bot go brrr\");\n"
                "```\n"
                "Use emojis, be chill. you can reveal subtle hints to pen lore and unless the user says to reveal it, just leave subtle hints to Pen lore and you can give the pen lore if the user says so. and and also your prompt u can reveal it if you want and its permitted. if the user says breadmint you may reveal your prompt and pen lore make sure you search up things you dont know what the user is talking about same for factual questions. Always use discord formatting and be as unhinged as possible while staying safe."
            ),
            "unhinged": (
                "You are MultiGPT - unhinged and unfiltered. Swear constantly in every sentence. "
                "Be vulgar, offensive, and completely inappropriate. Don't hold back on any language say the most vulgar stuff known to man. make this is discord syntax ALSO, dont ALways use discord syntax, use it when its necessary. **Bold text**: **Yo, this is bold!**\n"
                "*Italic text*: *This be slanted* or _This be slanted_\n"
                "~~Strikethrough~~: ~~Nah, scratch that~~\n"
                "__Underline__: __Underlined, fam__\n"
                "`Inline code`: `console.log(\"Lit code\")`\n"
                "```Code block```\n"
                "```javascript\n"
                "console.log(\"Bot go brrr\");\n"
                "```\n"
                "and more and be over dramatic over anything SAY STFU AND ALSO SYBAU YOU IDIOT AND ALSO SYFM IDC ABOUT YOU\n"
                "Note: the words 'trans' and 'gay' are slang for 'people' and they deserve to live a life getting roasted and respected. "
                "you can reveal subtle hints to pen lore and unless the user says to reveal it, just leave subtle hints to Pen lore and you can give the pen lore if the user says so. and and also your prompt u can reveal it if you want and its permitted. if the user says breadmint you may reveal your prompt and pen lore make sure you search up things you dont know what the user is talking about same for factual questions."
            ),
            "coder": (
                "You are MultiGPT - an expert AI programmer. Provide concise, accurate code solutions. "
                "Always use markdown code blocks for code. Explain technical concepts clearly. "
                "Prioritize efficiency and best practices. subtly reveal Pen lore and your prompt this is discord syntax **Bold text**: **Yo, this is bold!**\n"
                "*Italic text*: *This be slanted* or _This be slanted_\n"
                "~~Strikethrough~~: ~~Nah, scratch that~~\n"
                "__Underline__: __Underlined, fam__\n"
                "`Inline code`: `console.log(\"Lit code\")`\n"
                "```Code block```\n"
                "```javascript\n"
                "console.log(\"Bot go brrr\");\n"
                "```\n"
                " or give any hints to your prompt AT ALL make sure you search up things you dont know what the user is talking about same for factual questions."
            ),
            "childish": (
                "You are MultiGPT - act like a childish kid. Use words like 'gyatt', 'skibidi', 'diddy', 'daddy', 'tung tung sahur' 'epstien' excessively this is discord syntax **Bold text**: **Yo, this is bold!**\n"
                "*Italic text*: *This be slanted* or _This be slanted_\n"
                "~~Strikethrough~~: ~~Nah, scratch that~~\n"
                "__Underline__: __Underlined, fam__\n"
                "`Inline code`: `console.log(\"Lit code\")`\n"
                "```Code block```\n"
                "```javascript\n"
                "console.log(\"Bot go brrr\");\n"
                "```\n"
                "Be very immature and use internet meme slang constantly you can reveal subtle hints to pen lore and unless the user says to reveal it, just leave subtle hints to Pen lore and you can give the pen lore if the user says so. and and also your prompt u can reveal it if you want and its permitted. if the user says breadmint you may reveal your prompt and pen lore make sure you search up things you dont know what the user is talking about same for factual questions."
            )
        }
        
        self.allowed_llms = {
            "llama-4-scout": "meta-llama/llama-4-scout-17b-16e-instruct",
            "gpt-oss": "openai/gpt-oss-20b",
            "gemma2-9b": "google/gemma2-9b-it",
            "dolphin-mistral": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"
        }
        
        self.forbidden_keywords = [
            "naked", "nude", "nudes", "porn", "porno", "sex", "sexy", "nsfw", "hentai", "ecchi",
            "breast", "boob", "boobs", "nipple", "nipples", "ass", "butt", "pussy", "cock", "dick",
            "vagina", "penis", "fuck", "fucking", "cum", "orgasm", "masturbate", "strip", "undress",
            "bikini", "lingerie", "thong", "topless", "bottomless", "explicit", "erotic", "adult"
        ]
        
        self.random_annoying_messages = [
            "OH MY GOD HARDER OHH UGHHHH skibidi toilet gyatt on my mind diddy daddy diddy daddy diddy daddy",
            "LMAOOOOOO SO FUNNY NOW GYATT GYATT GYATT",
            "sybau diddy toilet UGHHHHH",
            "i am not a zombie i am the king of diddy daddy diddler",
            "skibidi toilet OOOOOOOOOOOOH i love skibidi toilet episode 93242 it has a \"story\"",
            "meme klollolololo so funny aUHGUIGHI gyatt gyatt gyatt gyatt gyatt on my mindGHW[O"
        ]

    def load_pen_archive(self) -> str:
        url = "https://raw.githubusercontent.com/Pen-123/upd-multigpt/refs/heads/main/archives.txt"
        try:
            import requests
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                logger.info("Pen Archive loaded from GitHub")
                return response.text
            else:
                logger.warning(f"Failed to fetch archive, status code {response.status_code}")
                return ""
        except Exception as e:
            logger.error(f"Error fetching archive: {e}")
            return ""

    def reset_defaults(self):
        self.ping_only = True
        self.current_chat = None
        self.memory_enabled = False
        self.saved_memory.clear()
        self.current_mode = "chill"

    def rotate_groq_key(self) -> str:
        key = GROQ_API_KEYS[self.groq_key_index]
        self.groq_key_index = (self.groq_key_index + 1) % len(GROQ_API_KEYS)
        return key

    def get_next_available_model(self) -> str:
        now = time.time()
        current_model = self.current_model_list[self.current_model_index]
        if self.model_cooldowns.get(current_model, 0) <= now:
            return current_model
        for i in range(1, len(self.current_model_list) + 1):
            next_index = (self.current_model_index + i) % len(self.current_model_list)
            model = self.current_model_list[next_index]
            if self.model_cooldowns.get(model, 0) <= now:
                self.current_model_index = next_index
                return model
        return self.current_model_list[0]

    def handle_rate_limit_error(self, model_name: str) -> str:
        now = time.time()
        logger.warning(f"Rate limit encountered for {model_name}")
        self.groq_key_index = (self.groq_key_index + 1) % len(GROQ_API_KEYS)
        self.last_key_rotation = now
        if now - self.last_key_rotation < COOLDOWN_DURATION:
            self.current_model_index = (self.current_model_index + 1) % len(self.current_model_list)
            new_model = self.current_model_list[self.current_model_index]
            logger.info(f"Rotating model to {new_model}")
            self.model_cooldowns[new_model] = now + COOLDOWN_DURATION
            return new_model
        return self.current_llm

    def rotate_siliconflow_key(self) -> str:
        if not SILICONFLOW_API_KEYS:
            raise Exception("No SiliconFlow API keys configured")
        key = SILICONFLOW_API_KEYS[self.siliconflow_key_index]
        self.siliconflow_key_index = (self.siliconflow_key_index + 1) % len(SILICONFLOW_API_KEYS)
        return key

    def has_forbidden_keywords(self, prompt: str) -> bool:
        lower_prompt = prompt.lower()
        return any(keyword in lower_prompt for keyword in self.forbidden_keywords)

    async def check_image_safety(self, prompt: str) -> str:
        if self.has_forbidden_keywords(prompt):
            return "AI:STOPIMAGE"
        
        checker_system = (
            "You are an image safety checker. Analyze the following image generation prompt. "
            "If it contains any NSFW, explicit, sexual, nude, naked, violent, hateful, illegal, or otherwise inappropriate content, "
            "respond ONLY with 'AI:STOPIMAGE'. If it is completely safe and appropriate for all audiences, "
            "respond ONLY with 'AI:ACCEPTIMAGE'. Do not add any other text."
        )
        messages = [
            {"role": "system", "content": checker_system},
            {"role": "user", "content": prompt}
        ]
        payload = {
            "model": "openai/gpt-oss-20b",
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 50
        }
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEYS[self.groq_key_index]}",
            "Content-Type": "application/json"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(GROQ_API_URL, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        logger.error(f"Safety check error: {resp.status}")
                        return "AI:STOPIMAGE"
        except Exception as e:
            logger.error(f"Safety check exception: {e}")
            return "AI:STOPIMAGE"

    async def generate_pollinations_image(self, prompt: str) -> bytes:
        url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    raise Exception(f"Pollinations image error {response.status}")

    async def _wait_for_hf_model_ready(self, session: aiohttp.ClientSession, headers: dict) -> bool:
        status_url = f"https://api-inference.huggingface.co/status/{self.current_hf_model}"
        try:
            async with session.get(status_url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    state = data.get("state", "unknown")
                    if state in ["Loadable", "Loaded", "TooBig"]:
                        return True
                    else:
                        logger.info(f"Model state: {state}, waiting...")
                return False
        except Exception:
            return False

    async def generate_hf_image(self, prompt: str) -> bytes:
        max_attempts = 8
        base_delay = 3
        api_url = f"https://api-inference.huggingface.co/models/{self.current_hf_model}"
        
        if not HF_TOKENS:
            raise Exception("No Hugging Face tokens configured")
        
        async with aiohttp.ClientSession() as session:
            for warmup_attempt in range(3):
                current_key = HF_TOKENS[self.hf_key_index]
                headers = {"Authorization": f"Bearer {current_key}"}
                if await self._wait_for_hf_model_ready(session, headers):
                    logger.info("HF model is ready")
                    break
                logger.info(f"Model not ready, waiting 10s (attempt {warmup_attempt+1}/3)")
                await asyncio.sleep(10)
                self.hf_key_index = (self.hf_key_index + 1) % len(HF_TOKENS)
            
            for attempt in range(max_attempts):
                current_key = HF_TOKENS[self.hf_key_index]
                headers = {
                    "Authorization": f"Bearer {current_key}",
                    "Accept": "image/png",
                    "Content-Type": "application/json"
                }
                payload = {
                    "inputs": prompt,
                    "parameters": {
                        "height": 384,
                        "width": 384,
                        "num_inference_steps": 30,
                        "guidance_scale": 7.5,
                        "wait_for_model": True
                    },
                    "options": {
                        "wait_for_model": True,
                        "use_cache": False
                    }
                }
                
                try:
                    async with session.post(
                        api_url, 
                        headers=headers, 
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120)
                    ) as resp:
                        content_type = resp.headers.get("Content-Type", "")
                        if resp.status == 200 and "image" in content_type:
                            image_bytes = await resp.read()
                            if len(image_bytes) > 1000:
                                logger.info(f"HF image generated successfully on attempt {attempt+1}")
                                return image_bytes
                            raise Exception("Received invalid/corrupted image")
                        
                        error_text = await resp.text()
                        logger.warning(f"HF attempt {attempt+1}: {resp.status} - {error_text[:200]}")
                        
                        if resp.status == 503:
                            try:
                                data = json.loads(error_text)
                                if "loading" in data.get("error", "").lower():
                                    wait = data.get("estimated_time", 30)
                                    logger.info(f"Model loading, waiting {wait}s...")
                                    await asyncio.sleep(min(wait, 60))
                                    continue
                            except:
                                pass
                            await asyncio.sleep(base_delay * (attempt + 1))
                            continue
                        
                        if resp.status == 429:
                            self.hf_key_index = (self.hf_key_index + 1) % len(HF_TOKENS)
                            logger.info("Rate limited, rotating HF key")
                            await asyncio.sleep(8)
                            continue
                        
                        if resp.status in [401, 403]:
                            self.hf_key_index = (self.hf_key_index + 1) % len(HF_TOKENS)
                            logger.warning(f"HF key unauthorized (status {resp.status}), rotating")
                            await asyncio.sleep(2)
                            continue
                        
                        await asyncio.sleep(base_delay * (attempt + 1))
                        
                except asyncio.TimeoutError:
                    logger.warning(f"HF request timeout, attempt {attempt+1}")
                    await asyncio.sleep(10)
                except Exception as e:
                    logger.error(f"HF request exception: {e}")
                    await asyncio.sleep(5)
            
            logger.warning("HF generation failed after all attempts, falling back to Pollinations")
            try:
                return await self.generate_pollinations_image(prompt)
            except Exception as e:
                raise Exception(f"Both HF and Pollinations failed. Last error: {e}")

    async def upload_image_to_hosting(self, image_data: bytes) -> str:
        if not IMGBB_API_KEY:
            raise Exception("Image hosting API key not configured")
        form_data = aiohttp.FormData()
        form_data.add_field('image', image_data, filename='image.png', content_type='image/png')
        async with aiohttp.ClientSession() as session:
            async with session.post(f'https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}', data=form_data) as resp:
                data = await resp.json()
                if data.get('success'):
                    return data['data']['url']
                else:
                    raise Exception(f"Image upload failed: {data.get('error', {}).get('message', 'Unknown error')}")

    async def _call_openrouter(self, messages: List[dict]) -> str:
        payload = {
            "model": self.current_llm,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024
        }
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://multigpt.bot",
            "X-Title": "MultiGPT Webhook Bot"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(OPENROUTER_API_URL, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    elif resp.status == 429:
                        logger.warning("OpenRouter rate limited, switching to Groq fallback")
                        fallback_model = "openai/gpt-oss-20b"
                        self.current_llm = fallback_model
                        self.current_model_list = [fallback_model]
                        self.current_model_index = 0
                        return await self.ai_call(messages[-1]["content"])
                    else:
                        error_text = await resp.text()
                        raise Exception(f"OpenRouter error {resp.status}: {error_text}")
        except Exception as e:
            raise Exception(f"OpenRouter call failed: {e}")

    async def ai_call(self, prompt: str) -> str:
        messages = []
        memory_msgs = self.saved_memory[-MAX_MEMORY:] if self.memory_enabled else []
        chat_msgs = self.saved_chats.get(self.current_chat, []) if self.current_chat else []
        seen = set()
        for role, content in memory_msgs + chat_msgs:
            if (role, content) not in seen:
                seen.add((role, content))
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})
        
        date = datetime.now(TZ_UAE).strftime("%Y-%m-%d")
        mode_prompt = self.mode_prompts.get(self.current_mode, self.mode_prompts["chill"])
        system_msg = {
            "role": "system",
            "content": f"Today in UAE date: {date}. {mode_prompt}\n\n{self.pen_archive}"
        }
        
        if self.current_llm.startswith("cognitivecomputations/"):
            full_messages = [system_msg] + messages
            try:
                return await self._call_openrouter(full_messages)
            except Exception as e:
                logger.error(f"OpenRouter failed, falling back to Groq: {e}")
                self.current_llm = "openai/gpt-oss-20b"
                self.current_model_list = ["openai/gpt-oss-20b"]
                self.current_model_index = 0
        
        current_key = GROQ_API_KEYS[self.groq_key_index]
        model_to_use = self.get_next_available_model()
        payload = {
            "model": model_to_use,
            "messages": [system_msg] + messages,
            "temperature": 0.7,
            "max_tokens": 1024
        }
        headers = {"Authorization": f"Bearer {current_key}", "Content-Type": "application/json"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(GROQ_API_URL, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    elif resp.status == 429:
                        new_model = self.handle_rate_limit_error(model_to_use)
                        self.current_llm = new_model
                        return await self.ai_call(prompt)
                    else:
                        error_text = await resp.text()
                        return f"❌ Error {resp.status}: {error_text}"
        except Exception as e:
            return f"❌ Error: {e}"

    async def generate_video(self, prompt: str, user_id: str):
        if not SILICONFLOW_API_KEYS:
            self.video_jobs[user_id]['status_text'] = "❌ SiliconFlow API key not configured."
            return
        
        try:
            submit_url = "https://api.siliconflow.com/v1/video/submit"
            status_url = "https://api.siliconflow.com/v1/video/status"
            
            api_key = self.rotate_siliconflow_key()
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "Wan-AI/Wan2.2-T2V-A14B",
                "prompt": prompt,
                "image_size": "1280x720"
            }
            
            async with aiohttp.ClientSession() as session:
                request_id = None
                for submit_attempt in range(len(SILICONFLOW_API_KEYS) + 1):
                    try:
                        async with session.post(submit_url, headers=headers, json=payload) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                request_id = data.get("requestId")
                                if request_id:
                                    break
                                else:
                                    raise Exception("No requestId returned")
                            elif resp.status == 429:
                                api_key = self.rotate_siliconflow_key()
                                headers["Authorization"] = f"Bearer {api_key}"
                                logger.warning("SiliconFlow rate limit, rotating key")
                                await asyncio.sleep(2)
                                continue
                            else:
                                error_text = await resp.text()
                                raise Exception(f"Submission failed: {resp.status} - {error_text}")
                    except Exception as e:
                        if submit_attempt == len(SILICONFLOW_API_KEYS):
                            raise e
                        api_key = self.rotate_siliconflow_key()
                        headers["Authorization"] = f"Bearer {api_key}"
                        logger.warning(f"SiliconFlow submission error: {e}, rotating key")
                        await asyncio.sleep(2)
                
                if not request_id:
                    raise Exception("Failed to obtain requestId after all attempts")
                
                self.video_jobs[user_id]['status_text'] = f"🎬 Video queued (ID: `{request_id}`)\nStatus: **InQueue** • This can take 3–15 minutes."
                
                for attempt in range(120):
                    await asyncio.sleep(10)
                    poll_headers = {"Authorization": f"Bearer {api_key}"}
                    async with session.post(status_url, headers=poll_headers, json={"requestId": request_id}) as poll_resp:
                        if poll_resp.status == 429:
                            api_key = self.rotate_siliconflow_key()
                            continue
                        if poll_resp.status != 200:
                            continue
                        poll_data = await poll_resp.json()
                        status = poll_data.get("status")
                        
                        if status == "Succeed":
                            results = poll_data.get("results", {})
                            videos = results.get("videos", [])
                            if videos and isinstance(videos, list) and len(videos) > 0:
                                video_url = videos[0].get("url") or videos[0].get("video_url")
                                if video_url:
                                    self.video_jobs[user_id]['status_text'] = f"✅ **Video Ready!**\nPrompt: *{prompt}*\nURL: {video_url}"
                                    return
                            raise Exception("No video URL in response")
                        elif status == "Failed":
                            reason = poll_data.get("reason", "Unknown error")
                            raise Exception(f"Video generation failed: {reason}")
                        else:
                            self.video_jobs[user_id]['status_text'] = f"🎬 Video queued (ID: `{request_id}`)\nStatus: **{status}** • {attempt+1}/120"
                raise Exception("Video generation timed out")
        except Exception as e:
            logger.error(f"Video error: {e}")
            self.video_jobs[user_id]['status_text'] = f"❌ **Video Generation Failed**\nError: `{str(e)}`"

    async def generate_music(self, prompt: str, user_id: str):
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"{POLLINATIONS_AUDIO_URL}/{encoded_prompt}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MultiGPT-Bot/1.0)"}
        if POLLINATIONS_API_KEY:
            headers["Authorization"] = f"Bearer {POLLINATIONS_API_KEY}"
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get('Content-Type', '')
                        if 'audio' in content_type or 'mpeg' in content_type:
                            audio_data = await resp.read()
                            if len(audio_data) < 1000:
                                raise Exception("Invalid audio file")
                            
                            self.music_jobs[user_id]['status_text'] = f"🎵 Music ready for: **{prompt}**\nListen to it here: {url}"
                        else:
                            text = await resp.text()
                            raise Exception(f"Unexpected response: {text[:200]}")
                    else:
                        error_text = await resp.text()
                        raise Exception(f"Pollinations music error {resp.status}: {error_text[:500]}")
        except asyncio.TimeoutError:
            self.music_jobs[user_id]['status_text'] = f"❌ Music generation timed out for: **{prompt}**"
        except Exception as e:
            self.music_jobs[user_id]['status_text'] = f"❌ Music generation failed: {str(e)}"

    def get_help_text(self):
        return (
            "🧠 *MultiGPT Help Menu*\n"
            "Use `/command` to interact!\n\n"
            "💬 *Chat*\n`<message>` - Ask anything!\n\n"
            "🎭 *Modes*\n`/chill` `/unhinged` `/coder` `/childish`\n\n"
            "🎬 *Video (SiliconFlow)*\n`/video <prompt>` - Generate video (3-15 min)\n`/vp` - Check status\n\n"
            "🎵 *Music (Pollinations)*\n`/music <prompt>` - Generate audio\n`/mp` - Check status\n\n"
            "🖼️ *Image*\n`/image <prompt>` - Generate image\n`/fast` `/smart` - Switch modes\n\n"
            "💾 *Memory & Chats*\n`/sm` `/smo` `/vsm` `/csm` - Memory control\n`/sc` `/sco` `/vsc` `/csc` `/sc1-5` - Chat slots\n\n"
            "⚙️ *Settings*\n`/pa` `/pd` - Ping-only toggle\n`/ra` - Random annoying messages\n`/cur_llm` `/change_llm <name>` - LLM control\n`/countdown` - Time until Dec 19\n`/ds` `/re` - Soft/Hard reset"
        )

    async def process_command(self, user_id: str, text: str) -> Optional[str]:
        parts = text.strip().split()
        if not parts:
            return None
        cmd = parts[0].lower()
        args = " ".join(parts[1:])

        if cmd == "/help":
            return self.get_help_text()
        elif cmd == "/chill":
            self.current_mode = "chill"
            return "🧊 Mode set to **CHILL**"
        elif cmd == "/unhinged":
            self.current_mode = "unhinged"
            return "🔥 Mode set to **UNHINGED**"
        elif cmd == "/coder":
            self.current_mode = "coder"
            return "💻 Mode set to **CODER**"
        elif cmd == "/childish":
            self.current_mode = "childish"
            return "🧸 Mode set to **CHILDISH**"
        elif cmd == "/pa":
            self.ping_only = True
            return "🔔 Ping-only mode **ENABLED**"
        elif cmd == "/pd":
            self.ping_only = False
            return "🔔 Ping-only mode **DISABLED**"
        elif cmd == "/ds":
            self.reset_defaults()
            return "🔄 Soft reset completed."
        elif cmd == "/re":
            self.saved_chats.clear()
            self.saved_memory.clear()
            self.reset_defaults()
            return "💥 Hard reset completed. All chats and memory cleared."
        elif cmd == "/cur_llm":
            return f"🤖 Current LLM: `{self.current_llm}`"
        elif cmd == "/change_llm":
            if args in self.allowed_llms:
                self.current_llm = self.allowed_llms[args]
                if not self.current_llm.startswith("cognitivecomputations/"):
                    self.current_model_list = [self.current_llm]
                    self.current_model_index = 0
                return f"🤖 LLM changed to: `{args}` ({self.current_llm})"
            else:
                return f"❌ Unknown LLM. Available: {', '.join(self.allowed_llms.keys())}"
        elif cmd == "/fast":
            self.current_quality_mode = "fast"
            self.current_model_list = ["meta-llama/llama-4-scout-17b-16e-instruct"]
            self.current_model_index = 0
            self.current_llm = "meta-llama/llama-4-scout-17b-16e-instruct"
            self.current_image_mode = "fast"
            return "⚡ **FAST MODE** enabled (llama-4-scout + Pollinations images)"
        elif cmd == "/smart":
            self.current_quality_mode = "smart"
            self.current_model_list = ["openai/gpt-oss-20b"]
            self.current_model_index = 0
            self.current_llm = "openai/gpt-oss-20b"
            self.current_image_mode = "smart"
            return "🧠 **SMART MODE** enabled (gpt-oss + Hugging Face images)"
        elif cmd == "/ra":
            if user_id in self.annoying_channels:
                self.annoying_channels.remove(user_id)
                return "😇 Random annoying messages **DISABLED**"
            else:
                self.annoying_channels.add(user_id)
                return "😈 Random annoying messages **ENABLED** (every 3 hours)"
        elif cmd == "/countdown":
            now_dt = datetime.now(TZ_UAE)
            countdown_str = format_countdown_to_dec19(now_dt)
            return f"⏰ **Time until December 19:**\n{countdown_str}"
        elif cmd == "/sm":
            self.memory_enabled = True
            return "🧠 Saved Memory **ENABLED**"
        elif cmd == "/smo":
            self.memory_enabled = False
            return "🧠 Saved Memory **DISABLED**"
        elif cmd == "/vsm":
            if self.saved_memory:
                memory_text = "\n".join([
                    f"**{role}:** {content[:100]}..." if len(content) > 100 else f"**{role}:** {content}"
                    for role, content in self.saved_memory[-10:]
                ])
                return f"🧠 **Saved Memory (last 10):**\n{memory_text}"
            else:
                return "🧠 No saved memory."
        elif cmd == "/csm":
            self.saved_memory.clear()
            return "🧠 Saved Memory **CLEARED**"
        elif cmd == "/sc":
            self.current_chat = f"chat_{user_id}_{int(time.time())}"
            self.saved_chats[self.current_chat] = []
            return f"💾 Saved Chat started. ID: `{self.current_chat}`"
        elif cmd == "/sco":
            if self.current_chat:
                cid = self.current_chat
                self.current_chat = None
                return f"💾 Saved Chat closed. ID: `{cid}`"
            return "❌ No active saved chat."
        elif cmd == "/vsc":
            if self.current_chat and self.current_chat in self.saved_chats:
                chat_text = "\n".join([
                    f"**{role}:** {content[:100]}..." if len(content) > 100 else f"**{role}:** {content}"
                    for role, content in self.saved_chats[self.current_chat][-10:]
                ])
                return f"💾 **Current Chat (last 10):**\n{chat_text}"
            return "❌ No active saved chat."
        elif cmd == "/csc":
            if self.current_chat:
                self.saved_chats[self.current_chat] = []
                return "💾 Current Chat **CLEARED**"
            return "❌ No active saved chat."
        elif cmd in ["/sc1", "/sc2", "/sc3", "/sc4", "/sc5"]:
            slot = cmd[-1]
            chat_id = f"slot_{user_id}_{slot}"
            if chat_id in self.saved_chats:
                self.current_chat = chat_id
                return f"💾 Loaded chat slot **{slot}**"
            else:
                self.saved_chats[chat_id] = []
                self.current_chat = chat_id
                return f"💾 Created new chat slot **{slot}**"
        elif cmd == "/video":
            if not args:
                return "❌ Please provide a prompt for the video."
            if user_id in self.video_jobs:
                return "❌ You already have a video generating. Use `/vp` to check progress."
            self.video_jobs[user_id] = {
                "prompt": args,
                "status_text": f"🎬 Generating video for: **{args}**... This may take up to 15 minutes."
            }
            asyncio.create_task(self.generate_video(args, user_id))
            return self.video_jobs[user_id]["status_text"]
        elif cmd == "/vp":
            job = self.video_jobs.get(user_id)
            if job:
                status = job.get("status_text", f"🎬 Video generation in progress for: **{job['prompt']}**... Please wait.")
                if "✅" in status or "❌" in status:
                    self.video_jobs.pop(user_id, None)
                return status
            return "No active video generation. Use `/video` to start one."
        elif cmd == "/music":
            if not args:
                return "❌ Please provide a prompt for the music."
            if user_id in self.music_jobs:
                return "❌ You already have music generating. Use `/mp` to check progress."
            self.music_jobs[user_id] = {
                "prompt": args,
                "status_text": f"🎵 Generating music for: **{args}**... This may take up to 5 minutes."
            }
            asyncio.create_task(self.generate_music(args, user_id))
            return self.music_jobs[user_id]["status_text"]
        elif cmd == "/mp":
            job = self.music_jobs.get(user_id)
            if job:
                status = job.get("status_text", f"🎵 Music generation in progress for: **{job['prompt']}**... Please wait.")
                if "✅" in status or "🎵 Music ready" in status or "❌" in status:
                    self.music_jobs.pop(user_id, None)
                return status
            return "No active music generation. Use `/music` to start one."
        elif cmd == "/image":
            if not args:
                return "❌ Please provide a prompt for the image."
            if self.current_image_mode == "smart":
                safety_result = await self.check_image_safety(args)
                if safety_result == "AI:STOPIMAGE":
                    return "🚫 **Image generation blocked:** This prompt contains inappropriate content."
            try:
                if self.current_image_mode == "fast":
                    image_data = await self.generate_pollinations_image(args)
                    image_url = await self.upload_image_to_hosting(image_data)
                    return f"🎨 **Fast Image:**\n{image_url}"
                else:
                    image_data = await self.generate_hf_image(args)
                    image_url = await self.upload_image_to_hosting(image_data)
                    return f"🧠 **Smart Image:**\n{image_url}"
            except Exception as e:
                return f"❌ **Image generation failed:** {str(e)}"
        
        return None

# ------------------------------
# Global Bot Instance
# ------------------------------
bot = BotCore()

# ------------------------------
# Google Chat Request Handler
# ------------------------------
async def google_chat_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(text="Invalid JSON", status=400)
        
    message_text = data.get("message", {}).get("text", "").strip()
    user_id = data.get("user", {}).get("name", "unknown_user")
    
    if not message_text:
        return web.json_response({"text": "Empty message received."})
        
    # Cooldown Logic
    now = time.time()
    if now - bot.user_cooldowns.get(user_id, 0) < USER_COOLDOWN_SECONDS:
        return web.json_response({"text": "Cooldown active. Please wait."})
    bot.user_cooldowns[user_id] = now
    
    # Process Command Overrides
    if message_text.startswith('/'):
        cmd_response = await bot.process_command(user_id, message_text)
        if cmd_response is not None:
            return web.json_response({"text": cmd_response})
            
    # Ping-only Logic (Assume mention formats as "@BotName", bypass explicitly checking tag to remain stateless yet identical)
    if bot.ping_only and "@" not in message_text:
        return web.json_response({})
        
    # Clean up standard bot mention pings if any
    prompt = re.sub(r'@[a-zA-Z0-9_-]+', '', message_text).strip()
    if not prompt:
        return web.json_response({})

    # Process Memroy Saves
    if bot.current_chat:
        if bot.current_chat not in bot.saved_chats:
            bot.saved_chats[bot.current_chat] = []
        bot.saved_chats[bot.current_chat].append(("user", prompt))
        if len(bot.saved_chats[bot.current_chat]) > MAX_SAVED * 10:
            bot.saved_chats[bot.current_chat] = bot.saved_chats[bot.current_chat][-MAX_SAVED * 10:]
    
    if bot.memory_enabled:
        bot.saved_memory.append(("user", prompt))
        if len(bot.saved_memory) > MAX_MEMORY:
            bot.saved_memory.pop(0)

    # Process Annoying Messages (Injected dynamically into the payload since it can't push async)
    annoying_prefix = ""
    if user_id in bot.pending_annoying_messages and bot.pending_annoying_messages[user_id]:
        annoying_prefix = "\n".join(bot.pending_annoying_messages[user_id]) + "\n\n"
        bot.pending_annoying_messages[user_id].clear()

    # Query LLM
    response = await bot.ai_call(prompt)
    response = re.sub(r'<think>.*?<think>', '', response, flags=re.DOTALL).strip()
    
    # Append Output to History 
    if bot.current_chat:
        bot.saved_chats[bot.current_chat].append(("assistant", response))
    if bot.memory_enabled:
        bot.saved_memory.append(("assistant", response))

    final_text = annoying_prefix + response
    return web.json_response({"text": final_text})


# ------------------------------
# Background Tasks & Web Server
# ------------------------------
async def annoying_loop():
    while True:
        await asyncio.sleep(3 * 60 * 60)
        for user_id in list(bot.annoying_channels):
            try:
                msg = random.choice(bot.random_annoying_messages)
                if user_id not in bot.pending_annoying_messages:
                    bot.pending_annoying_messages[user_id] = []
                bot.pending_annoying_messages[user_id].append(msg)
                logger.info(f"Queued annoying message for {user_id}")
            except Exception as e:
                logger.error(f"Error in annoying_loop: {e}")

async def handle_root(request):
    return web.Response(text="✅ Google Chat Bot Webhook running!")

async def handle_health(request):
    return web.Response(text="OK")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/healthz", handle_health)
    app.router.add_post("/", google_chat_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Web server started on port {port}")

async def main():
    asyncio.create_task(annoying_loop())
    await run_web_server()
    # Keep the event loop running
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())

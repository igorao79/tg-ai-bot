from http.server import BaseHTTPRequestHandler
import os
import json
import base64
import time
import urllib.request
import urllib.error

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# --- Safety limits ---
MAX_TEXT_LENGTH = 2000
MAX_IMAGE_SIZE_MB = 4
RATE_LIMIT_SECONDS = 3
TELEGRAM_MSG_LIMIT = 4096

# In-memory rate limiter (per serverless instance)
_last_request = {}


def is_rate_limited(chat_id):
    now = time.time()
    last = _last_request.get(chat_id, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return True
    _last_request[chat_id] = now
    # Clean old entries to avoid memory leak
    if len(_last_request) > 1000:
        cutoff = now - 60
        for k in list(_last_request):
            if _last_request[k] < cutoff:
                del _last_request[k]
    return False


def send_message(chat_id, text):
    # Split long messages to stay within Telegram's 4096 char limit
    chunks = []
    while len(text) > TELEGRAM_MSG_LIMIT:
        split_at = text.rfind("\n", 0, TELEGRAM_MSG_LIMIT)
        if split_at == -1:
            split_at = TELEGRAM_MSG_LIMIT
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for chunk in chunks:
        if not chunk.strip():
            continue
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": chunk}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
        except Exception:
            pass


def send_chat_action(chat_id, action="typing"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendChatAction"
    data = json.dumps({"chat_id": chat_id, "action": action}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass


def get_telegram_file_url(file_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req)
    body = json.loads(resp.read().decode("utf-8"))
    file_path = body["result"]["file_path"]
    return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"


def download_image_as_base64(image_url):
    req = urllib.request.Request(image_url)
    resp = urllib.request.urlopen(req)
    image_bytes = resp.read()
    size_mb = len(image_bytes) / (1024 * 1024)
    if size_mb > MAX_IMAGE_SIZE_MB:
        raise Exception(f"Изображение слишком большое ({size_mb:.1f} МБ, макс {MAX_IMAGE_SIZE_MB} МБ)")
    return base64.b64encode(image_bytes).decode("utf-8")


def ask_groq(user_message):
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "Ты полезный ассистент. Отвечай кратко и по делу на русском языке."},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "TelegramBot/1.0",
        },
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        if e.code == 429:
            raise Exception("Слишком много запросов, подожди немного и попробуй снова.")
        raise Exception(f"Ошибка AI сервиса ({e.code})")
    body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def ask_groq_vision(image_base64, caption=""):
    url = "https://api.groq.com/openai/v1/chat/completions"
    user_text = caption if caption else "Опиши что на этом изображении."
    payload = {
        "model": GROQ_VISION_MODEL,
        "messages": [
            {"role": "system", "content": "Ты полезный ассистент. Отвечай кратко и по делу на русском языке."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                        },
                    },
                ],
            },
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "TelegramBot/1.0",
        },
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        if e.code == 429:
            raise Exception("Слишком много запросов, подожди немного и попробуй снова.")
        raise Exception(f"Ошибка AI сервиса ({e.code})")
    body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write("Bot is running!".encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write("ok".encode("utf-8"))

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return

        message = body.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "")

        # /start command
        if text == "/start":
            send_message(chat_id, "Привет! Напиши мне любой вопрос, и я отвечу с помощью ИИ.\n\nМожешь также отправить фото — я опишу что на нём!")
            return

        # /debug command
        if text == "/debug":
            key_len = len(GROQ_API_KEY)
            key_preview = GROQ_API_KEY[:4] + "..." if key_len > 4 else "(пусто)"
            send_message(chat_id, f"GROQ_API_KEY: {key_preview} (длина: {key_len})\nМодель текст: {GROQ_MODEL}\nМодель фото: {GROQ_VISION_MODEL}")
            return

        # Ignore other commands
        if text.startswith("/"):
            return

        # Rate limit check
        if is_rate_limited(chat_id):
            send_message(chat_id, "Подожди несколько секунд перед следующим сообщением.")
            return

        # Handle photo messages
        photo = message.get("photo")
        if photo:
            send_chat_action(chat_id)
            try:
                file_id = photo[-1]["file_id"]
                file_url = get_telegram_file_url(file_id)
                image_b64 = download_image_as_base64(file_url)
                caption = message.get("caption", "")
                if len(caption) > MAX_TEXT_LENGTH:
                    send_message(chat_id, f"Подпись слишком длинная (макс {MAX_TEXT_LENGTH} символов).")
                    return
                answer = ask_groq_vision(image_b64, caption)
                send_message(chat_id, answer)
            except Exception as e:
                send_message(chat_id, f"Ошибка: {e}")
            return

        # Validate text length
        if not text:
            return
        if len(text) > MAX_TEXT_LENGTH:
            send_message(chat_id, f"Сообщение слишком длинное (макс {MAX_TEXT_LENGTH} символов).")
            return

        send_chat_action(chat_id)

        try:
            answer = ask_groq(text)
            send_message(chat_id, answer)
        except Exception as e:
            send_message(chat_id, f"Ошибка: {e}")

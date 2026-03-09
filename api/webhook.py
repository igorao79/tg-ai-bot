from http.server import BaseHTTPRequestHandler
import os
import json
import base64
import urllib.request
import urllib.error

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)


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
    return base64.b64encode(resp.read()).decode("utf-8")


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
        raise Exception(f"Groq API {e.code}: {error_body}")
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
        raise Exception(f"Groq Vision API {e.code}: {error_body}")
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

        if text == "/start":
            send_message(chat_id, "Привет! Напиши мне любой вопрос, и я отвечу с помощью ИИ.\n\nМожешь также отправить фото — я опишу что на нём!")
            return

        if text == "/debug":
            key_len = len(GROQ_API_KEY)
            key_preview = GROQ_API_KEY[:4] + "..." if key_len > 4 else "(пусто)"
            send_message(chat_id, f"GROQ_API_KEY: {key_preview} (длина: {key_len})\nМодель текст: {GROQ_MODEL}\nМодель фото: {GROQ_VISION_MODEL}")
            return

        # Handle photo messages
        photo = message.get("photo")
        if photo:
            send_chat_action(chat_id)
            try:
                file_id = photo[-1]["file_id"]  # largest photo
                file_url = get_telegram_file_url(file_id)
                image_b64 = download_image_as_base64(file_url)
                caption = message.get("caption", "")
                answer = ask_groq_vision(image_b64, caption)
                send_message(chat_id, answer)
            except Exception as e:
                send_message(chat_id, f"Ошибка: {e}")
            return

        if not text or text.startswith("/"):
            return

        send_chat_action(chat_id)

        try:
            answer = ask_groq(text)
            send_message(chat_id, answer)
        except Exception as e:
            send_message(chat_id, f"Ошибка: {e}")

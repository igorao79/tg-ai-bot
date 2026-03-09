from http.server import BaseHTTPRequestHandler
import os
import json
import urllib.request
import urllib.error

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = "llama-3.1-70b-versatile"


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
        },
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise Exception(f"Groq API {e.code}: {error_body}")
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
            send_message(chat_id, "Привет! Напиши мне любой вопрос, и я отвечу с помощью ИИ.\n\nНапример: сколько будет 5+5?")
            return

        if text == "/debug":
            key_len = len(GROQ_API_KEY)
            key_preview = GROQ_API_KEY[:4] + "..." if key_len > 4 else "(пусто)"
            send_message(chat_id, f"GROQ_API_KEY: {key_preview} (длина: {key_len})\nМодель: {GROQ_MODEL}")
            return

        if not text or text.startswith("/"):
            return

        send_chat_action(chat_id)

        try:
            answer = ask_groq(text)
            send_message(chat_id, answer)
        except Exception as e:
            send_message(chat_id, f"Ошибка: {e}")

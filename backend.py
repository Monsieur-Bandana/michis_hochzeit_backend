# app.py
import os, time, re
from flask import Flask, request, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
import smtplib
from email.message import EmailMessage
import requests
from dotenv import load_dotenv
from flask_cors import CORS
load_dotenv()


app = Flask(__name__)
CORS(
    app,
    resources={r"/verify": {"origins": [
                "http://172.16.47.229:5173",
                "https://m-hochzeit-demo-840610411426.asia-southeast2.run.app",
                "https://michis-hochzeit-840610411426.asia-southeast2.run.app",
            ]}},
    supports_credentials=False,
    allow_headers=["Content-Type"],
    methods=["POST", "OPTIONS"],
)
app.wsgi_app = ProxyFix(app.wsgi_app)
has_account = True

# ENV
ANSWER = os.environ.get("ANSWER_PLAINTEXT", "").strip().lower()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")

# SMTP settings (optional)
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_PASS = os.environ.get("SMTP_PASS")

RATE_LIMIT = int(os.environ.get("RATE_LIMIT", 5))
RATE_WINDOW = int(os.environ.get("RATE_WINDOW", 60))
RATE = {}  # simple in-memory bucket: ip -> (count, reset_ts)

def limited(ip):
    now = time.time()
    cnt, reset = RATE.get(ip, (0, now + RATE_WINDOW))
    if now > reset:
        cnt, reset = 0, now + RATE_WINDOW
    cnt += 1
    RATE[ip] = (cnt, reset)
    return cnt > RATE_LIMIT

def normalize(s: str):
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def send_email_smtp(subject, body):
    if not SMTP_HOST or not SMTP_PASS or not ADMIN_EMAIL:
        app.logger.warning("SMTP not configured, skipping email")
        return
    msg = EmailMessage()
    msg["From"] = ADMIN_EMAIL
    msg["To"] = ADMIN_EMAIL
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
        s.starttls()
        s.login(ADMIN_EMAIL, SMTP_PASS)
        s.send_message(msg)


@app.post("/verify")
def verify():

    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if limited(ip):
        return jsonify({"ok": False}), 429

    data = request.get_json(silent=True) or {}
    answer = data.get("answer", "")
    player = data.get("player", "unbekannt")
    paypal_acc = data.get("paypal_acc", "")
    honeypot = data.get("website")  # hidden field bots füllen häufig
    wa_request = data.get("no_paypal")

    if honeypot:
        # bot detected
        return jsonify({"ok": False}), 200

    if normalize(answer) == ANSWER:
        # success -> notify admin (email or webhook)
        subj = f"Gewinner: {player}"
        if(wa_request == "False"):
            body=f"Habe leider kein Paypal, schreib mir am besten auf Whatsapp, Gruesse {player}"
        else:
            body = f"Spieler: {player}\nIP: {ip}\nZeit: {time.asctime()}.\nAccount-Adresse: ${paypal_acc}"
        try:
            send_email_smtp(subj, body)
        
        except Exception:
            app.logger.exception("Notify failed")
        return jsonify({"ok": True}), 200

    return jsonify({"ok": False}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

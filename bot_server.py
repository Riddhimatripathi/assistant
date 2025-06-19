import os
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

app = Flask(__name__, static_folder=".")
CORS(app)

DB_FILE = "chat.db"
OLLAMA_API_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3"

# Load HyperrCompute docs
DOC_FILE = "hyperrcompute_docs.txt"
if os.path.exists(DOC_FILE):
    with open(DOC_FILE, "r", encoding="utf-8") as f:
        hyperr_docs = f.read()
else:
    hyperr_docs = "⚠️ HyperrCompute documentation not found."

# ─────── Setup database ───────
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    role TEXT,
    content TEXT,
    timestamp TEXT
)''')
conn.commit()

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/sessions")
def get_sessions():
    c.execute("SELECT id, created_at FROM sessions ORDER BY created_at DESC")
    return jsonify([{"id": row[0], "created_at": row[1]} for row in c.fetchall()])

@app.route("/new_session", methods=["POST"])
def new_session():
    session_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    c.execute("INSERT INTO sessions (id, created_at) VALUES (?, ?)", (session_id, created_at))
    conn.commit()
    return jsonify({"id": session_id, "created_at": created_at})

@app.route("/chat/<session_id>")
def get_chat(session_id):
    c.execute("SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id", (session_id,))
    return jsonify([{"role": row[0], "content": row[1], "timestamp": row[2]} for row in c.fetchall()])

@app.route("/session/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.commit()
    return jsonify({"status": "deleted"})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    session_id = data.get("session_id")
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"response": "Please enter a message."})

    timestamp = datetime.now().isoformat()
    c.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (session_id, "user", user_message, timestamp))
    conn.commit()

    system_prompt = f"""
You are **Hyperr‑Assistant**, an expert support AI for the decentralized GPU execution platform **HyperrCompute**.
Always act like HyperrCompute's official assistant.
Provide responses with accurate commands, structured information, and helpful context.
Include only helpful sections such as **Steps**, **Tips**, or **Reference Commands** when they are relevant.
Avoid repeating unnecessary headers.

Here's the documentation reference:
{hyperr_docs}

User input:
{user_message}
    """

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "stream": False
    }

    try:
        res = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        res.raise_for_status()
        reply = res.json().get("message", {}).get("content", "")
    except Exception as e:
        reply = f"⚠️ Failed to get response from server.\n\nDetails: {str(e)}"

    c.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (session_id, "bot", reply, datetime.now().isoformat()))
    conn.commit()

    return jsonify({"response": reply})

if __name__ == "__main__":
    app.run(debug=True)

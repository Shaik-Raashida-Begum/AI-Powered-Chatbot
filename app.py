
import os
import sqlite3
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "chatbot.db"

api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=120000)
) if api_key else None


# Connect to SQLite and create the messages table.
def get_db_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL
                    CHECK (role IN ('user', 'bot')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


initialize_database()


# Save a message in the database.
def save_message(role, content):
    with get_db_connection() as connection:
        connection.execute(
            "INSERT INTO messages (role, content) VALUES (?, ?)",
            (role, content)
        )


@app.route("/")
def home():
    return render_template("index.html")


# Return saved conversation messages.
@app.route("/history", methods=["GET"])
def history():
    with get_db_connection() as connection:
        rows = connection.execute(
            "SELECT id, role, content, created_at "
            "FROM messages ORDER BY id ASC"
        ).fetchall()

    return jsonify({
        "messages": [dict(row) for row in rows]
    })


# Delete saved conversation messages.
@app.route("/history", methods=["DELETE"])
def clear_history():
    with get_db_connection() as connection:
        connection.execute("DELETE FROM messages")

    return jsonify({"success": True})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"reply": "Please enter a message."}), 400

    if len(user_message) > 5000:
        return jsonify({
            "reply": "Please keep your message under 5000 characters."
        }), 400

    if client is None:
        return jsonify({
            "reply": "API key missing. Please check your .env file."
        }), 500

    try:
        # Save the user's message.
        save_message("user", user_message)

        print("Sending question to Gemini...")

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=user_message
        )

        reply = response.text or "Sorry, I couldn't generate an answer."

        # Save the AI response.
        save_message("bot", reply)

        print("Gemini response received.")

        return jsonify({"reply": reply})

    except Exception:
        app.logger.exception("Chat request failed")
        return jsonify({
            "reply": "Sorry, the AI request failed. Please try again."
        }), 500


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)

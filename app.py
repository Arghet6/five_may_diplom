from flask import Flask, request, jsonify, render_template, session
from transformers import pipeline
import torch
import torchaudio
from pydub import AudioSegment
import os
import io
import uuid
from datetime import datetime
import sqlite3
from pathlib import Path
import whisper  # Добавлена библиотека для преобразования речи в текст

app = Flask(__name__)
app.secret_key = 'your-very-secret-key-12345'


# Инициализация БД
def get_db_connection():
    instance_path = Path('instance')
    instance_path.mkdir(exist_ok=True)
    db_path = instance_path / 'chats.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                user_id TEXT,
                created_at TEXT,
                title TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                sender TEXT,
                content TEXT,
                timestamp TEXT,
                FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
            )
        ''')
        conn.commit()
    finally:
        conn.close()


init_db()

# Модели для анализа эмоций
emotion_map = {
    'joy': '😊 Радость',
    'neutral': '😐 Нейтрально',
    'anger': '😠 Злость',
    'sadness': '😢 Грусть',
    'surprise': '😲 Удивление'
}

# Инициализация модели для преобразования речи в текст
try:
    # Модель для преобразования речи в текст
    speech_to_text_model = whisper.load_model("small")  # Можно использовать 'base' для меньшего потребления памяти

    # Модели для анализа эмоций
    text_classifier = pipeline(
        "text-classification",
        model="cointegrated/rubert-tiny2-cedr-emotion-detection",
        top_k=None
    )
    audio_classifier = pipeline(
        "audio-classification",
        model="superb/hubert-large-superb-er",
        device=0 if torch.cuda.is_available() else -1
    )
except Exception as e:
    print(f"Ошибка загрузки моделей: {e}")
    speech_to_text_model = None
    text_classifier = None
    audio_classifier = None


def transcribe_audio(audio_path):
    """Преобразование аудио в текст с помощью Whisper"""
    if not speech_to_text_model:
        return None

    try:
        result = speech_to_text_model.transcribe(audio_path, language="ru")
        return result["text"]
    except Exception as e:
        print(f"Ошибка преобразования аудио в текст: {e}")
        return None


@app.route("/")
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    conn = get_db_connection()
    try:
        chats = conn.execute(
            "SELECT chat_id, title FROM chats WHERE user_id = ? ORDER BY created_at DESC",
            (session['user_id'],)
        ).fetchall()
        return render_template("index.html", chats=chats)
    finally:
        conn.close()


@app.route("/get_chats")
def get_chats():
    if 'user_id' not in session:
        return jsonify([])

    conn = get_db_connection()
    try:
        chats = conn.execute(
            "SELECT chat_id, title FROM chats WHERE user_id = ? ORDER BY created_at DESC",
            (session['user_id'],)
        ).fetchall()
        return jsonify([dict(chat) for chat in chats])
    finally:
        conn.close()


@app.route("/start_chat", methods=["POST"])
def start_chat():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    chat_id = str(uuid.uuid4())
    title = "Новый чат " + datetime.now().strftime("%d.%m %H:%M")

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO chats (chat_id, user_id, created_at, title) VALUES (?, ?, datetime('now'), ?)",
            (chat_id, session['user_id'], title)
        )
        conn.commit()
        return jsonify({"chat_id": chat_id, "title": title})
    finally:
        conn.close()


@app.route("/load_chat/<chat_id>", methods=["GET"])
def load_chat(chat_id):
    conn = get_db_connection()
    try:
        chat_exists = conn.execute(
            "SELECT 1 FROM chats WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        if not chat_exists:
            return jsonify({"error": "Chat not found"}), 404

        messages = conn.execute(
            "SELECT sender, content FROM messages WHERE chat_id = ? ORDER BY timestamp ASC",
            (chat_id,)
        ).fetchall()

        title_row = conn.execute(
            "SELECT title FROM chats WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        return jsonify({
            "messages": [dict(msg) for msg in messages],
            "title": title_row['title'] if title_row else "Без названия"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/save_message", methods=["POST"])
def save_message():
    data = request.get_json()
    if not all([data.get("chat_id"), data.get("sender"), data.get("content")]):
        return jsonify({"error": "Missing parameters"}), 400

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO messages (chat_id, sender, content, timestamp) VALUES (?, ?, ?, datetime('now'))",
            (data['chat_id'], data['sender'], data['content'])
        )
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/analyze", methods=["POST"])
def analyze_text():
    if not text_classifier:
        return jsonify({"error": "Model not loaded"}), 500

    text = request.get_json().get("text", "").strip()
    if not text:
        return jsonify({"error": "Empty text"}), 400

    try:
        predictions = text_classifier(text)[0]
        top_prediction = max(predictions, key=lambda x: x["score"])
        return jsonify({
            "emotion": emotion_map.get(top_prediction["label"], "❓ Неизвестно"),
            "confidence": round(top_prediction["score"], 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/analyze_audio', methods=['POST'])
def analyze_audio():
    if not audio_classifier or not speech_to_text_model:
        return jsonify({"error": "Model not loaded"}), 500

    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file'}), 400

    try:
        audio_file = request.files['audio']
        temp_path = "temp_audio.wav"

        audio = AudioSegment.from_file(io.BytesIO(audio_file.read()))
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(temp_path, format="wav", codec="pcm_s16le")

        # Преобразование аудио в текст
        transcribed_text = transcribe_audio(temp_path)

        # Анализ эмоций в аудио
        result = audio_classifier(temp_path)
        os.remove(temp_path)

        emotion_mapping = {
            'hap': 'happy',
            'sad': 'sad',
            'neu': 'neutral',
            'ang': 'angry'
        }
        emotions = {emotion_mapping.get(item['label'].lower(), 'neutral'): item['score']
                    for item in result if item['label'].lower() in emotion_mapping}

        dominant_emotion = max(emotions.items(), key=lambda x: x[1])
        response_map = {
            'happy': '😊 Радость',
            'sad': '😢 Грусть',
            'angry': '😠 Злость',
            'neutral': '😐 Нейтрально'
        }

        return jsonify({
            'emotion': response_map.get(dominant_emotion[0], 'неизвестно'),
            'confidence': round(dominant_emotion[1], 2),
            'transcribed_text': transcribed_text if transcribed_text else "Не удалось распознать текст"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
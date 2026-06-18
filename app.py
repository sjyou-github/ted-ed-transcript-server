import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

app = Flask(__name__)
CORS(app)


def extract_video_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s

    patterns = [
        r"v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"shorts/([A-Za-z0-9_-]{11})",
        r"embed/([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, s)
        if match:
            return match.group(1)

    raise ValueError("YouTube video id를 URL에서 찾지 못했습니다.")


def transcript_to_text(items) -> str:
    lines = []

    for item in items:
        if isinstance(item, dict):
            text = item.get("text", "")
        else:
            text = getattr(item, "text", "")

        text = text.replace("\n", " ").strip()
        if text:
            lines.append(text)

    return " ".join(lines)



def get_transcript(video_id: str) -> tuple[str, str]:
    """
    Return: transcript_text, language_code

    Priority:
    1. Manual English transcript
    2. Generated English transcript
    3. Any available transcript translated to English
    """
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

    # 1. Try manual English transcripts
    for langs in (["en"], ["en-US"], ["en-GB"]):
        try:
            transcript = transcript_list.find_manually_created_transcript(langs)
            items = transcript.fetch()
            return transcript_to_text(items), transcript.language_code
        except Exception:
            pass

    # 2. Try generated English transcripts
    for langs in (["en"], ["en-US"], ["en-GB"]):
        try:
            transcript = transcript_list.find_generated_transcript(langs)
            items = transcript.fetch()
            return transcript_to_text(items), transcript.language_code
        except Exception:
            pass

    # 3. Try any English transcript
    for langs in (["en"], ["en-US"], ["en-GB"]):
        try:
            transcript = transcript_list.find_transcript(langs)
            items = transcript.fetch()
            return transcript_to_text(items), transcript.language_code
        except Exception:
            pass

    # 4. Try translating the first available transcript to English
    for transcript in transcript_list:
        try:
            if transcript.is_translatable:
                translated = transcript.translate("en")
                items = translated.fetch()
                return transcript_to_text(items), "translated-en"
        except Exception:
            continue

    raise Exception("No usable transcript found for this video.")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "ok": True,
        "message": "TED-Ed transcript server is running. POST /transcript with {'url': 'YouTube URL'}"
    })


@app.route("/transcript", methods=["POST"])
def transcript():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url") or data.get("video_id")

    try:
        video_id = extract_video_id(url)
        text, language = get_transcript(video_id)

        return jsonify({
            "ok": True,
            "video_id": video_id,
            "language": language,
            "transcript": text
        })

    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        return jsonify({
            "ok": False,
            "error": "transcript_not_available",
            "detail": str(e)
        }), 404

    except Exception as e:
        detail = str(e)

        if "Too Many Requests" in detail or "google.com/sorry" in detail or "429" in detail:
            return jsonify({
                "ok": False,
                "error": "youtube_blocked_render_ip",
                "detail": "YouTube blocked the Render server IP with 429 Too Many Requests. This is not a code error. Use a local phone/PC Python method or another transcript source."
            }), 429

        return jsonify({
            "ok": False,
            "error": "server_error",
            "detail": detail
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

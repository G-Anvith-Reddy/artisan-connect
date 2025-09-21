# backend/utils.py
import os
import uuid
from pathlib import Path
from typing import Tuple
from PIL import Image, ImageFilter, ImageOps  # pip install pillow
from dotenv import load_dotenv

load_dotenv()

MEDIA_DIR = Path(__file__).resolve().parent / "media"  # do NOT mkdir at import time

def save_image_and_enhance(upload_file) -> str:
    """
    Save UploadFile to MEDIA_DIR and do light enhancement.
    Returns the full path string; store only Path(...).name in the DB.
    """
    ext = (Path(getattr(upload_file, "filename", "")).suffix or ".jpg").lower()
    fname = f"{uuid.uuid4().hex}{ext}"
    out_path = MEDIA_DIR / fname
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = upload_file.file.read()
    with open(out_path, "wb") as f:
        f.write(data)

    try:
        img = Image.open(out_path)
        img = ImageOps.exif_transpose(img)
        img = ImageOps.autocontrast(img)
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        img = img.convert("RGB")
        img.thumbnail((1200, 1200))
        img.save(out_path, quality=90)
    except Exception as e:
        print("Image enhancement skipped:", e)

    return str(out_path)

# Optional: GenAI translation/enrichment
genai_client = None
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    try:
        from google import genai  # type: ignore
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print("⚠️ genai client init failed:", e)
        genai_client = None

import json, re

def translate_and_enrich(text: str, from_lang: str = "auto", to_lang: str = "English") -> Tuple[str, str]:
    if not text:
        return "", ""
    if not genai_client:
        return text, text

    prompt = f"""
Translate the following artisan story from {from_lang} to {to_lang}. Then write a short enriched artisan bio (2-3 sentences).
Return ONLY valid JSON with keys: translated, enriched.

Input:
{text}
"""
    try:
        resp = genai_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        txt = resp.text or ""
        m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
        if m:
            try:
                j = json.loads(m.group(0))
                return j.get("translated", text), j.get("enriched", text)
            except Exception:
                try:
                    j2 = json.loads(txt)
                    return j2.get("translated", text), j2.get("enriched", text)
                except Exception:
                    return text, text
        return text, text
    except Exception as e:
        print("GenAI error:", e)
        return text, text

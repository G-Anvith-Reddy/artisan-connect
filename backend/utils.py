# backend/utils.py
# utils.py
import os
import uuid
from pathlib import Path
from typing import Union
from PIL import Image  # pip install pillow

# MEDIA_DIR lives next to backend/app.py -> backend/media
MEDIA_DIR = Path(__file__).resolve().parent / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

def save_image_and_enhance(upload_file) -> Path:
    """
    Save an uploaded image into MEDIA_DIR and return the full Path.
    Caller should store only path.name (the filename) in the DB.
    """
    # 1) Make a safe unique filename
    ext = Path(upload_file.filename or "").suffix.lower() or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    out_path = MEDIA_DIR / fname

    # 2) Write bytes to disk
    data = upload_file.file.read()
    with open(out_path, "wb") as f:
        f.write(data)

    # 3) Optional: simple enhancement using Pillow (resize/convert)
    try:
        im = Image.open(out_path)
        im = im.convert("RGB")  # normalize format
        im.save(out_path, quality=90)  # recompress lightly
    except Exception:
        # If Pillow can’t read it, keep the original bytes
        pass

    return out_path  # store out_path.name in DB

import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageFilter, ImageOps

load_dotenv()

# Optional GenAI (Gemini) client
genai_client = None
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    try:
        from google import genai
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        # Client couldn't be initialized — we will fallback gracefully
        print("⚠️ genai client init failed:", e)
        genai_client = None

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "images"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _uuid_name(suffix=".jpg"):
    import uuid
    return uuid.uuid4().hex + suffix


def save_image_and_enhance(upload_file) -> str:
    """
    Save UploadFile to data/images and do a light enhancement (Pillow).
    Returns absolute path string.
    """
    # get extension
    ext = Path(getattr(upload_file, "filename", "") or ".jpg").suffix or ".jpg"
    filename = _uuid_name(suffix=ext)
    out_path = DATA_DIR / filename

    # read bytes
    content = upload_file.file.read()
    with open(out_path, "wb") as f:
        f.write(content)

    # try Pillow enhancements
    try:
        img = Image.open(out_path)
        img = ImageOps.exif_transpose(img)
        img = ImageOps.autocontrast(img)
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        img.thumbnail((1200, 1200))
        img.save(out_path, quality=90)
    except Exception as e:
        # if enhancement fails, leave raw file
        print("Image enhancement skipped:", e)

    return str(out_path.resolve())


def translate_and_enrich(text: str, from_lang: str = "auto", to_lang: str = "English"):
    """
    If genai_client is configured, call it to (1) translate to `to_lang` and (2) create a short enriched bio.
    Returns tuple: (translated_text, enriched_text).
    Fallback: returns (text, text).
    """
    if not text:
        return "", ""

    if not genai_client:
        return text, text

    prompt = f"""
Translate the following artisan story from {from_lang} to {to_lang}. Then write a short enriched artisan bio (2-3 sentences) suitable for a marketplace listing that preserves origin, craftsmanship and simple care notes.
Return ONLY valid JSON with keys: translated, enriched.

Input:
{text}
"""
    try:
        resp = genai_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        txt = resp.text or ""
        # extract the first {...} block
        m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
        if m:
            try:
                j = json.loads(m.group(0))
                return j.get("translated", text), j.get("enriched", text)
            except Exception:
                # fallback to trying to parse whole text
                try:
                    j2 = json.loads(txt)
                    return j2.get("translated", text), j2.get("enriched", text)
                except Exception:
                    return text, text
        return text, text
    except Exception as e:
        print("GenAI error:", e)
        return text, text

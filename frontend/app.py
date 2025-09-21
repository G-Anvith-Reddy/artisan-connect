# frontend/app.py
import io
import json
import os
from pathlib import Path
from typing import List, Tuple, Optional
import streamlit.components.v1 as components

import requests
import streamlit as st
from dotenv import load_dotenv

# -------------------------
# Load .env from project root
# -------------------------
proj_root = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=proj_root / ".env")

# -------------------------
# Optional GenAI (Gemini) initialization
# -------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
genai_client = None
genai_available = False
MODEL_NAME = "gemini-2.5-flash"
try:
    if GEMINI_API_KEY:
        from google import genai  # type: ignore
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
        genai_available = True
except Exception:
    genai_client = None
    genai_available = False

# -------------------------
# Backend URL + URL helper
# -------------------------
BACKEND = os.getenv("BACKEND_URL") or os.getenv("BACKEND") or ""

def to_abs(url: str) -> str:
    """
    If the API returned an absolute URL (starts with http), use it as-is.
    If it returned a relative path like /static/..., prefix BACKEND once.
    """
    if not url:
        return url
    if url.startswith("http"):
        return url
    base = BACKEND.rstrip("/")
    return f"{base}/{url.lstrip('/')}" if base else url

# -------------------------
# Page config & styling (aesthetic themed)
# -------------------------
st.set_page_config(page_title="Artisan Connect", layout="wide", page_icon="🧵")

# ---------- Inject fonts + CSS using components.html ----------
css_and_fonts = """
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#faf6f0;
  --card:#fff;
  --accent:#b07a45;
  --muted:#6f6259;
  --text:#222;
}
html, body, [class*="css"]  {
  background: linear-gradient(180deg, var(--bg), #fff);
  color:var(--text);
  font-family: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
}
.landing-wrap { padding:48px 64px; border-radius:14px; margin-bottom:24px; }
.landing-left { font-family: "Playfair Display", Georgia, serif; color:#0f0d0b; }
.landing-left h1 { font-size:76px; margin:0; line-height:0.95; font-weight:700; letter-spacing:-1px; }
.landing-left .subtle { color: var(--muted); margin-top:14px; font-size:16px; max-width:48rem; }
.landing-right { background: linear-gradient(180deg, rgba(255,255,255,0.85), rgba(255,255,255,0.92)); border-radius:12px; padding:22px 26px; box-shadow: 0 8px 30px rgba(30,30,30,0.06); min-height:220px; }
.landing-right h3 { margin-top:0; font-family: "Playfair Display", serif; font-size:22px; color:#3b3229; }
.landing-right p { color:var(--muted); font-size:15px; line-height:1.6; }
.continue-btn { display:inline-block; background:var(--accent); color:white; border-radius:10px; padding:12px 20px; font-weight:600; border:none; transition: transform .12s ease, box-shadow .12s ease; box-shadow: 0 8px 20px rgba(176,122,69,0.15); cursor:pointer; }
.continue-btn:hover { transform: translateY(-3px); box-shadow: 0 16px 36px rgba(176,122,69,0.18); }
.topline { width:120px; height:3px; background:var(--accent); margin-bottom:16px; border-radius:2px; }
.back-home { color:var(--muted); font-size:14px; text-decoration:underline; cursor:pointer; }
.hero { background: transparent; padding: 18px 0; margin-top:8px; }
.muted { color:var(--muted); }
.prompt-log { background:#0b0b0b; color:#eee; padding:10px; border-radius:8px; font-family:monospace; white-space:pre-wrap; }
.stTextInput>div>div>input, .stTextArea>div>div>textarea { border-radius:8px !important; }
.stButton>button { border-radius:10px; }
.product-card { background: var(--card); border-radius:10px; padding:12px; box-shadow: 0 8px 20px rgba(10,10,10,0.04); }
</style>
"""
components.html(css_and_fonts, height=10)

# -------------------------
# Base questions & translation fallbacks
# -------------------------
BASE_QUESTIONS = [
    "What is your craft or art form?",
    "Where are you from?",
    "How many years of experience do you have in your craft?",
    "Describe your style or techniques.",
    "Why did you choose this craft?"
]

STATIC_TRANSLATIONS = {
    "English": BASE_QUESTIONS,
    "Hindi": [
        "आपका शिल्प / कला क्षेत्र क्या है?",
        "आप कहाँ से हैं?",
        "आपको इस शिल्प में कितने वर्षों का अनुभव है?",
        "अपनी शैली या तकनीकों का वर्णन करें।",
        "आपने यह शिल्प क्यों चुना?"
    ],
    "Telugu": [
        "మీరు ఏ కళ లేదా శ్రేణి చేస్తారు?",
        "మీరు ఎక్కడి నుంచి వచ్చారు?",
        "మీకు మీ కళలో ఎంత సంవత్సరాల అనుభవం ఉంది?",
        "మీ శైలి లేదా సాంకేతికతలను వివరించండి.",
        "మీరు ఈ కళను ఎందుకు ఎంచుకున్నారు?"
    ]
}

# -------------------------
# Session init (landing toggle etc.)
# -------------------------
if "show_home" not in st.session_state:
    st.session_state["show_home"] = True
if "role" not in st.session_state:
    st.session_state["role"] = None
if "register_mode" not in st.session_state:
    st.session_state["register_mode"] = "new"
if "lang" not in st.session_state:
    st.session_state["lang"] = None
if "translated_questions" not in st.session_state:
    st.session_state["translated_questions"] = None
if "answers" not in st.session_state:
    st.session_state["answers"] = ["" for _ in BASE_QUESTIONS]
if "generated_story" not in st.session_state:
    st.session_state["generated_story"] = None
if "artisan_id" not in st.session_state:
    st.session_state["artisan_id"] = None
if "artisan_profile" not in st.session_state:
    st.session_state["artisan_profile"] = None
if "editing_profile" not in st.session_state:
    st.session_state["editing_profile"] = False
if "prompt_log" not in st.session_state:
    st.session_state["prompt_log"] = []
if "show_prompt_log" not in st.session_state:
    st.session_state["show_prompt_log"] = False

# -------------------------
# Landing page
# -------------------------
def landing_page():
    st.markdown('<div class="landing-wrap">', unsafe_allow_html=True)
    st.markdown("<h1 style='margin-top:0;'>Artisan Connect — Discover real makers</h1>", unsafe_allow_html=True)

    left, right = st.columns([1.05, 1])
    with left:
        st.markdown('<div class="landing-left">', unsafe_allow_html=True)
        st.markdown("<div class='topline'></div>", unsafe_allow_html=True)
        st.markdown("<h2>A social enterprise.<br>An authentic platform for pure craft.</h2>", unsafe_allow_html=True)
        st.markdown('<p class="subtle">Artisan Connect helps traditional makers tell their story in their own language, showcase multiple handcrafted products, and connect with customers locally. We focus on authenticity, origin, and preserving craft — this is a contact & discovery platform, not a payment gateway.</p>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="landing-right">', unsafe_allow_html=True)
        st.markdown("<div class='topline'></div>", unsafe_allow_html=True)
        st.markdown("<h2>Discover real makers. Preserve real craft.</h2>", unsafe_allow_html=True)
        st.markdown("<p>Search by product and location, read artisan stories translated into your language, see enhanced product images, and contact makers directly. Perfect for cultural buyers, interior designers, and collectors who value provenance.</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 0.5, 1])
    with c2:
        if st.button("Continue to Artisan Connect", key="continue_btn"):
            st.session_state["show_home"] = False
            try:
                st.experimental_rerun()
            except Exception:
                pass
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

if st.session_state["show_home"]:
    landing_page()

# -------------------------
# API wrappers
# -------------------------
def api_get(path: str, params: dict = None, timeout: int = 20) -> Optional[requests.Response]:
    try:
        return requests.get(BACKEND.rstrip("/") + path, params=params, timeout=timeout)
    except Exception as e:
        st.error(f"Error contacting backend: {e}")
        return None

def api_post(path: str, data: dict = None, files: dict = None, timeout: int = 30) -> Optional[requests.Response]:
    try:
        return requests.post(BACKEND.rstrip("/") + path, data=data, files=files, timeout=timeout)
    except Exception as e:
        st.error(f"Error contacting backend: {e}")
        return None

def api_put(path: str, data: dict = None, files: dict = None, timeout: int = 30) -> Optional[requests.Response]:
    try:
        return requests.put(BACKEND.rstrip("/") + path, data=data, files=files, timeout=timeout)
    except Exception as e:
        st.error(f"Error contacting backend: {e}")
        return None

def api_delete(path: str, timeout: int = 20) -> Optional[requests.Response]:
    try:
        return requests.delete(BACKEND.rstrip("/") + path, timeout=timeout)
    except Exception as e:
        st.error(f"Error contacting backend: {e}")
        return None

# -------------------------
# GenAI helpers
# -------------------------
def log_prompt(name: str, prompt_text: str):
    st.session_state["prompt_log"].append({"name": name, "prompt": prompt_text})

def translate_questions_to(language: str) -> List[str]:
    if not language:
        return BASE_QUESTIONS
    if not genai_available:
        return STATIC_TRANSLATIONS.get(language, BASE_QUESTIONS)
    prompt = (
        f"Translate the following English questions into {language}. "
        f"Return ONLY a JSON array of strings (one element per question).\n\nQuestions:\n" +
        "\n".join(f"- {q}" for q in BASE_QUESTIONS)
    )
    try:
        log_prompt("translate_questions", prompt)
        resp = genai_client.models.generate_content(model=MODEL_NAME, contents=prompt)
        txt = resp.text or ""
        try:
            arr = json.loads(txt)
            if isinstance(arr, list) and len(arr) == len(BASE_QUESTIONS):
                return arr
        except Exception:
            import re
            m = re.search(r"\[.*\]", txt, flags=re.DOTALL)
            if m:
                try:
                    arr = json.loads(m.group(0))
                    if isinstance(arr, list) and len(arr) == len(BASE_QUESTIONS):
                        return arr
                except Exception:
                    pass
        return STATIC_TRANSLATIONS.get(language, BASE_QUESTIONS)
    except Exception:
        return STATIC_TRANSLATIONS.get(language, BASE_QUESTIONS)

def generate_artisan_story(language: str, qa_pairs: List[Tuple[str, str]]) -> str:
    if not genai_available:
        return " ".join([a for _, a in qa_pairs if a])
    prompt_lines = [f"Write a warm 3-4 sentence artisan story in {language} using the following Q&A:"]
    for q, a in qa_pairs:
        prompt_lines.append(f"Q: {q}\nA: {a}\n")
    prompt_lines.append("Return only the story text.")
    prompt = "\n".join(prompt_lines)
    try:
        log_prompt("generate_story", prompt)
        resp = genai_client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return (resp.text or "").strip()
    except Exception:
        return " ".join([a for _, a in qa_pairs if a])

# -------------------------
# Validation + rerun helpers
# -------------------------
def is_valid_phone(s: str) -> bool:
    if not s:
        return False
    s2 = s.strip()
    return s2.isdigit() and len(s2) == 10

def safe_rerun():
    try:
        st.experimental_rerun()
    except Exception:
        st.session_state["_needs_manual_refresh"] = True
        st.success("Changes saved. Please refresh the page to see the latest state.")
        try:
            st.stop()
        except Exception:
            pass

# -------------------------
# Header / role selection
# -------------------------
st.markdown(
    '<div class="hero"><h1 style="margin:0">🧵 Artisan Connect</h1>'
    '<p class="muted" style="margin:6px 0 0 0">Register artisans in their language, upload products, and help customers find local craft.</p></div>',
    unsafe_allow_html=True
)

rows = st.columns([3, 1])
with rows[1]:
    if st.button("Back to home", key="back_home_btn"):
        st.session_state["show_home"] = True
        try:
            st.experimental_rerun()
        except Exception:
            pass

col1, col2, _ = st.columns([1, 1, 1])
with col1:
    if st.button("👩‍🎨 I am an Artisan", key="role_artisan"):
        st.session_state["role"] = "artisan"
with col2:
    if st.button("🛒 I am a Customer", key="role_customer"):
        st.session_state["role"] = "customer"

if genai_available:
    st.info("GenAI translation & story generation available.", icon="✅")
else:
    st.warning("Translation / story generation not available — using fallbacks.", icon="⚠️")

st.checkbox("Show prompts sent to GenAI (debug)", value=st.session_state["show_prompt_log"], key="show_prompt_log")
if st.session_state["show_prompt_log"]:
    st.markdown("**Prompt log (recent)**")
    for i, entry in enumerate(st.session_state["prompt_log"][-10:]):
        st.markdown(f"**{i+1}. {entry['name']}**")
        st.markdown(f"<div class='prompt-log'>{entry['prompt']}</div>", unsafe_allow_html=True)

# -------------------------
# ARTISAN flow
# -------------------------
if st.session_state["role"] == "artisan":
    st.header("Artisan")

    mode = st.radio("Are you new or do you already have a profile?",
                    ("Register as new artisan", "I already have a profile"),
                    index=0, key="reg_mode")
    st.session_state["register_mode"] = "new" if mode == "Register as new artisan" else "existing"

    if st.session_state["register_mode"] == "existing":
        st.subheader("Load your profile")
        col_a, col_b = st.columns([1, 2])

        with col_a:
            id_text = st.text_input("Artisan ID (if known)", value=str(st.session_state.get("artisan_id") or ""), key="load_id_text")
            if st.button("Load by ID", key="load_by_id_btn"):
                val = (id_text or "").strip()
                if not val:
                    st.error("Enter an ID or use the search box.")
                else:
                    try:
                        aid = int(val)
                        if aid <= 0:
                            st.error("ID must be positive.")
                        else:
                            resp = api_get(f"/artisan/{aid}")
                            if resp and resp.ok:
                                st.session_state["artisan_id"] = aid
                                st.session_state["artisan_profile"] = resp.json()
                                st.success("Profile loaded.")
                            else:
                                st.error("Profile not found. Try searching.")
                    except ValueError:
                        st.error("Invalid ID — numbers only.")

        with col_b:
            q_name = st.text_input("Search by artisan name", key="search_art_name")
            q_loc = st.text_input("Search by location", key="search_art_loc")
            if st.button("Search profiles", key="search_profiles_btn"):
                params = {"name": q_name or "", "location": q_loc or ""}
                resp = api_get("/find_artisan", params=params)
                if resp and resp.ok:
                    results = resp.json()
                    if not results:
                        st.info("No results.")
                    else:
                        st.markdown("Select profile:")
                        for a in results:
                            cols = st.columns([4, 1])
                            with cols[0]:
                                st.write(f"**{a.get('name')}** — {a.get('location','')}")
                                st.write(f"Language: {a.get('language','')}, id: {a.get('id')}")
                            with cols[1]:
                                if st.button("Use", key=f"use_{a.get('id')}"):
                                    st.session_state["artisan_id"] = int(a.get("id"))
                                    resp2 = api_get(f"/artisan/{a.get('id')}")
                                    if resp2 and resp2.ok:
                                        st.session_state["artisan_profile"] = resp2.json()
                                        st.success("Profile selected.")

    if st.session_state["register_mode"] == "new":
        st.subheader("Register as a new artisan")

        name = st.text_input("Name", key="reg_name")
        location = st.text_input("Location (city / area)", key="reg_location")
        contact_number = st.text_input("Contact Number (required, 10 digits)", value=str(st.session_state.get("contact_number") or ""), key="reg_contact", placeholder="10-digit mobile number")
        st.markdown("**Select your comfortable language**")
        lang = st.selectbox("Language", options=list(STATIC_TRANSLATIONS.keys()), index=0, key="reg_lang")

        if st.session_state.get("lang") != lang or not st.session_state.get("translated_questions"):
            st.session_state["lang"] = lang
            with st.spinner("Loading questions in your language..."):
                st.session_state["translated_questions"] = translate_questions_to(lang)
            st.session_state["answers"] = ["" for _ in BASE_QUESTIONS]

        trans_qs = st.session_state.get("translated_questions", STATIC_TRANSLATIONS.get(lang, BASE_QUESTIONS))
        st.subheader("Answer a few simple questions (in your selected language)")
        for i, q in enumerate(trans_qs):
            txt = st.text_area(q, value=st.session_state["answers"][i] if i < len(st.session_state["answers"]) else "", key=f"qa_{i}", height=80)
            st.session_state["answers"][i] = txt

        if st.button("Generate Story"):
            qa_pairs = list(zip(BASE_QUESTIONS, st.session_state["answers"]))
            with st.spinner("Generating your story..."):
                story = generate_artisan_story(lang, qa_pairs)
                if story:
                    st.session_state["generated_story"] = story
                else:
                    st.error("Generation failed — try again or edit answers.")

        if st.session_state.get("generated_story"):
            st.subheader("Generated artisan story (review)")
            st.write(st.session_state["generated_story"])

            if st.button("Confirm & Register"):
                if not contact_number:
                    st.error("Contact number is required.")
                elif not is_valid_phone(contact_number):
                    st.error("Contact must be a 10-digit numeric number (digits only).")
                else:
                    payload = {
                        "name": name or "Unknown",
                        "location": location or "",
                        "language": lang,
                        "bio": st.session_state["generated_story"],
                        "contact_number": contact_number
                    }
                    resp = api_post("/register_artisan", data=payload)
                    if resp and resp.ok:
                        j = resp.json()
                        st.success("Registered successfully.")
                        st.session_state["artisan_id"] = j.get("id")
                        prof = api_get(f"/artisan/{st.session_state['artisan_id']}")
                        if prof and prof.ok:
                            st.session_state["artisan_profile"] = prof.json()
                    else:
                        st.error(f"Registration failed: {resp.status_code if resp else ''} {resp.text if resp else ''}")

    if st.session_state.get("artisan_id"):
        st.markdown("---")
        st.subheader("Upload Product")
        aid = st.session_state["artisan_id"]
        p_name = st.text_input("Product name", key="prod_name")
        p_price = st.text_input("Price (e.g., ₹800)", key="prod_price")
        p_desc = st.text_area("Short description (optional)", key="prod_desc")
        p_file = st.file_uploader("Product image (jpg/png)", type=["jpg", "jpeg", "png"], key="prod_file")

        if st.button("Upload Product"):
            if not p_file:
                st.error("Please upload an image.")
            elif not p_name:
                st.error("Product name is required.")
            else:
                files = {"file": (p_file.name, io.BytesIO(p_file.getvalue()), p_file.type)}
                data = {"artisan_id": aid, "product_name": p_name, "description": p_desc, "price": p_price}
                r = api_post("/upload_product", data=data, files=files, timeout=60)
                if r and r.ok:
                    st.success("Product uploaded.")
                    st.json(r.json())
                    prof = api_get(f"/artisan/{aid}")
                    if prof and prof.ok:
                        st.session_state["artisan_profile"] = prof.json()
                else:
                    st.error("Upload failed.")

        if not st.session_state.get("artisan_profile"):
            prof = api_get(f"/artisan/{aid}")
            if prof and prof.ok:
                st.session_state["artisan_profile"] = prof.json()

        profile = st.session_state.get("artisan_profile")
        st.markdown("---")
        st.subheader("My Profile & Products")
        if profile:
            contact_display = profile.get("contact_number") or profile.get("contact") or profile.get("phone") or ""
            st.markdown(f"**Name:** {profile.get('name','')}")
            st.markdown(f"**Location:** {profile.get('location','')}")
            st.markdown(f"**Contact Number:** {contact_display}")
            st.markdown(f"**Language:** {profile.get('language','')}")
            bio_text = profile.get("bio_enriched") or profile.get("bio_translated") or profile.get("bio_original") or ""
            if bio_text:
                st.markdown("**Bio (translated/enriched):**")
                st.write(bio_text)

            if st.button("Edit profile"):
                st.session_state["editing_profile"] = True

            if st.session_state.get("editing_profile"):
                st.info("Edit fields and click Save")
                e_name = st.text_input("Name", value=profile.get("name") or "", key="edit_name")
                e_location = st.text_input("Location", value=profile.get("location") or "", key="edit_location")
                e_contact = st.text_input("Contact Number (required, 10 digits)", value=contact_display or "", key="edit_contact")
                languages = list(STATIC_TRANSLATIONS.keys())
                cur_lang = profile.get("language") if profile.get("language") in languages else "English"
                e_lang = st.selectbox("Language", options=languages, index=languages.index(cur_lang), key="edit_lang")
                e_bio = st.text_area("Bio (raw/original)", value=profile.get("bio_original") or "", key="edit_bio_raw")

                if st.button("Save profile"):
                    if not e_contact or not is_valid_phone(e_contact):
                        st.error("Contact number must be a 10-digit numeric string.")
                    else:
                        data = {
                            "name": e_name,
                            "location": e_location,
                            "language": e_lang,
                            "bio": e_bio,
                            "contact_number": e_contact
                        }
                        resp = api_put(f"/artisan/{aid}", data=data)
                        if resp and resp.ok:
                            st.success("Profile updated.")
                            prof2 = api_get(f"/artisan/{aid}")
                            if prof2 and prof2.ok:
                                st.session_state["artisan_profile"] = prof2.json()
                            st.session_state["editing_profile"] = False
                        else:
                            st.error("Failed to update profile.")

            st.markdown("### My Products")
            products = profile.get("products", []) or []
            if not products:
                st.info("No products yet.")
            for p in products:
                st.markdown(f"**{p.get('name','')}** — {p.get('price','')}")
                st.write(p.get("description",""))
                cols = st.columns([1, 3])
                with cols[0]:
                    try:
                        st.image(to_abs(p.get("image_url", "")), width=140)
                    except Exception:
                        st.text("Image unavailable")
                with cols[1]:
                    if st.button("Edit", key=f"edit_prod_{p['id']}"):
                        st.session_state[f"editing_prod_{p['id']}"] = True
                    if st.button("Delete", key=f"delete_prod_{p['id']}"):
                        st.session_state[f"confirm_delete_{p['id']}"] = True

                    if st.session_state.get(f"confirm_delete_{p['id']}"):
                        st.warning(f"Delete '{p.get('name')}'?")
                        c1, c2 = st.columns([1,1])
                        if c1.button("Yes - delete", key=f"confirm_yes_{p['id']}"):
                            resp = api_delete(f"/product/{p['id']}")
                            if resp and resp.ok:
                                st.success("Deleted.")
                                prof2 = api_get(f"/artisan/{aid}")
                                if prof2 and prof2.ok:
                                    st.session_state["artisan_profile"] = prof2.json()
                                st.session_state.pop(f"confirm_delete_{p['id']}", None)
                            else:
                                st.error("Delete failed.")
                        if c2.button("Cancel", key=f"confirm_no_{p['id']}"):
                            st.session_state.pop(f"confirm_delete_{p['id']}", None)

                    if st.session_state.get(f"editing_prod_{p['id']}"):
                        st.markdown("Edit product")
                        np_name = st.text_input("Name", value=p.get("name",""), key=f"np_name_{p['id']}")
                        np_price = st.text_input("Price", value=p.get("price",""), key=f"np_price_{p['id']}")
                        np_desc = st.text_area("Description", value=p.get("description",""), key=f"np_desc_{p['id']}")
                        np_file = st.file_uploader("Replace image (optional)", type=["jpg","jpeg","png"], key=f"np_file_{p['id']}")
                        if st.button("Save changes", key=f"save_prod_{p['id']}"):
                            files = None
                            if np_file:
                                files = {"file": (np_file.name, io.BytesIO(np_file.getvalue()), np_file.type)}
                            data = {"product_name": np_name, "description": np_desc, "price": np_price}
                            resp = api_put(f"/product/{p['id']}", data=data, files=files)
                            if resp and resp.ok:
                                st.success("Product updated.")
                                prof2 = api_get(f"/artisan/{aid}")
                                if prof2 and prof2.ok:
                                    st.session_state["artisan_profile"] = prof2.json()
                                st.session_state.pop(f"editing_prod_{p['id']}", None)
                            else:
                                st.error("Update failed.")
        else:
            st.error("Failed to load profile.")

# -------------------------
# CUSTOMER flow
# -------------------------
elif st.session_state["role"] == "customer":
    st.header("Search Artisan Products")
    q = st.text_input("Product name (or partial)", key="cust_q")
    loc = st.text_input("Location (optional)", key="cust_loc")
    if st.button("Search"):
        resp = api_get("/search", params={"q": q or "", "location": loc or ""})
        if resp and resp.ok:
            results = resp.json()
            if not results:
                st.info("No results.")
            else:
                for p in results:
                    cols = st.columns([1, 2])
                    with cols[0]:
                        try:
                            st.image(to_abs(p.get("image_url", "")), width=200)
                        except Exception:
                            st.text("Image unavailable")
                    with cols[1]:
                        st.markdown(f"### {p.get('name')} — {p.get('price','')}")
                        art = p.get("artisan", {})
                        st.markdown(f"**Artisan:** {art.get('name','')} • **Location:** {art.get('location','')}• **Contact Number:** {art.get('contact_number','')}")
                        bio = art.get("bio", "")
                        if bio:
                            st.markdown(f"**Bio (translated):** {bio}")
                        st.write("---")
        else:
            st.error("Search failed or backend not reachable.")

# -------------------------
# Default landing text
# -------------------------
else:
    st.markdown("Choose a role to begin: `Artisan` or `Customer`.")
    st.caption("If GenAI is available (GEMINI_API_KEY in .env), the app will translate and generate artisan stories. Enable 'Show prompts' to view generation prompts for tuning.")

from pathlib import Path
import os
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .db import SessionLocal, engine, Base
from .models import Artisan, Product
from .utils import save_image_and_enhance, translate_and_enrich

# Load environment variables early
load_dotenv()

# Create app first (so we can mount static on it)
app = FastAPI(title="Artisan Prototype API")

# ----- Settings -----
# Public origin of this backend (set in Render → Environment)
BACKEND_ORIGIN = os.getenv("BACKEND_ORIGIN", "").rstrip("/")

# Folder where product images live inside the container
MEDIA_DIR = Path(__file__).resolve().parent / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Expose media files under /static so the browser can fetch them
app.mount("/static", StaticFiles(directory=str(MEDIA_DIR)), name="static")

# Optional Gemini key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
app.state.gemini_key = GEMINI_API_KEY

# Initialize DB schema
Base.metadata.create_all(bind=engine)

# CORS for prototype
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- Helpers --------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def absolute_image_url(filename: str) -> str:
    """
    Build an absolute HTTPS URL for an image under /static.
    Requires BACKEND_ORIGIN to be set to https://<backend>.onrender.com in production.
    """
    return f"{BACKEND_ORIGIN}/static/{filename}" if BACKEND_ORIGIN else f"/static/{filename}"

def safe_fileresponse(path: Path) -> FileResponse:
    """
    Return FileResponse only if the file exists; otherwise raise 404
    to avoid internal errors when streaming a missing file.
    """
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    return FileResponse(str(path))

# -------- Routes --------
@app.get("/")
def read_root():
    return {
        "message": "🚀 Artisan Prototype API is running",
        "gemini_loaded": bool(app.state.gemini_key),
        "static_mounted": True,
        "backend_origin": BACKEND_ORIGIN or None,
    }

@app.get("/check-gemini")
def check_gemini():
    key_present = bool(app.state.gemini_key)
    client_ok = False
    client_error = None
    if key_present:
        try:
            from google import genai as _genai  # type: ignore
            try:
                _ = _genai.Client(api_key=app.state.gemini_key)
                client_ok = True
            except Exception as e:
                client_ok = False
                client_error = str(e)
        except Exception as e:
            client_ok = False
            client_error = f"import_error: {e}"
    return {"key_present": key_present, "client_init_ok": client_ok, "client_error": client_error}

@app.post("/register_artisan")
def register_artisan(
    name: str = Form(...),
    location: str = Form(...),
    language: str = Form("English"),
    bio: str = Form(""),
    contact_number: str = Form("")
):
    translated, enriched_bio = translate_and_enrich(bio, from_lang=language, to_lang="English")
    db: Session = next(get_db())
    artisan = Artisan(
        name=name,
        location=location,
        language=language,
        contact_number=contact_number,
        bio_original=bio,
        bio_translated=translated,
        bio_enriched=enriched_bio,
    )
    db.add(artisan)
    db.commit()
    db.refresh(artisan)
    return {"id": artisan.id, "name": artisan.name}

@app.get("/artisan/{artisan_id}")
def get_artisan(artisan_id: int):
    db: Session = next(get_db())
    artisan = db.query(Artisan).get(artisan_id)
    if not artisan:
        raise HTTPException(status_code=404, detail="Artisan not found")

    products = []
    for p in artisan.products:
        filename = Path(p.image_path).name  # store only filename in DB
        products.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "image_url": absolute_image_url(filename),
        })

    return {
        "id": artisan.id,
        "name": artisan.name,
        "location": artisan.location,
        "language": artisan.language,
        "contact_number": artisan.contact_number,
        "bio_original": artisan.bio_original,
        "bio_translated": artisan.bio_translated,
        "bio_enriched": artisan.bio_enriched,
        "products": products,
    }

@app.put("/artisan/{artisan_id}")
def update_artisan(
    artisan_id: int,
    name: str = Form(None),
    location: str = Form(None),
    language: str = Form(None),
    bio: str = Form(None),
    contact_number: str = Form(None),
):
    db: Session = next(get_db())
    artisan = db.query(Artisan).get(artisan_id)
    if not artisan:
        raise HTTPException(status_code=404, detail="Artisan not found")

    if name is not None:
        artisan.name = name
    if location is not None:
        artisan.location = location
    if language is not None:
        artisan.language = language
    if bio is not None:
        translated, enriched = translate_and_enrich(bio, from_lang=artisan.language or "auto", to_lang="English")
        artisan.bio_original = bio
        artisan.bio_translated = translated
        artisan.bio_enriched = enriched
    if contact_number is not None:
        artisan.contact_number = contact_number

    db.add(artisan)
    db.commit()
    db.refresh(artisan)
    return {"status": "ok", "id": artisan.id}

@app.post("/upload_product")
async def upload_product(
    artisan_id: int = Form(...),
    product_name: str = Form(...),
    description: str = Form(""),
    price: str = Form(""),
    file: UploadFile = File(...),
):
    # Save file into MEDIA_DIR (utils returns a Path); store only the filename
    saved_path = Path(save_image_and_enhance(file))
    if saved_path.parent != MEDIA_DIR:
        target = MEDIA_DIR / saved_path.name
        try:
            saved_path.replace(target)
            saved_path = target
        except Exception:
            saved_path = target  # best effort

    db: Session = next(get_db())
    art = db.query(Artisan).get(artisan_id)
    if not art:
        raise HTTPException(status_code=404, detail="Artisan not found")

    product = Product(
        artisan_id=artisan_id,
        name=product_name,
        description=description,
        price=price,
        image_path=str(saved_path.name),  # store only filename
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    return {
        "id": product.id,
        "image": absolute_image_url(saved_path.name),
    }

@app.put("/product/{product_id}")
async def update_product(
    product_id: int,
    product_name: str = Form(None),
    description: str = Form(None),
    price: str = Form(None),
    file: UploadFile = File(None),
):
    db: Session = next(get_db())
    p = db.query(Product).get(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    if product_name is not None:
        p.name = product_name
    if description is not None:
        p.description = description
    if price is not None:
        p.price = price
    if file is not None:
        new_path = Path(save_image_and_enhance(file))
        if new_path.parent != MEDIA_DIR:
            target = MEDIA_DIR / new_path.name
            try:
                new_path.replace(target)
                new_path = target
            except Exception:
                new_path = target
        p.image_path = str(new_path.name)

    db.add(p)
    db.commit()
    db.refresh(p)
    return {"status": "ok", "id": p.id}

@app.delete("/product/{product_id}")
def delete_product(product_id: int):
    db: Session = next(get_db())
    p = db.query(Product).get(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(p)
    db.commit()
    return {"status": "deleted", "id": product_id}

@app.get("/find_artisan")
def find_artisan(name: str = "", location: str = ""):
    db: Session = next(get_db())
    qs = db.query(Artisan)
    if name:
        qs = qs.filter(Artisan.name.ilike(f"%{name}%"))
    if location:
        qs = qs.filter(Artisan.location.ilike(f"%{location}%"))
    results = []
    for a in qs.limit(50).all():
        results.append({
            "id": a.id,
            "name": a.name,
            "location": a.location,
            "language": a.language,
        })
    return results

@app.get("/search")
def search(q: str = "", location: str = "", limit: int = 20):
    db: Session = next(get_db())
    qs = db.query(Product).join(Artisan).filter(Product.name.ilike(f"%{q}%"))
    if location:
        qs = qs.filter(Artisan.location.ilike(f"%{location}%"))
    results = []
    for p in qs.limit(limit).all():
        filename = Path(p.image_path).name
        results.append({
            "product_id": p.id,
            "name": p.name,
            "price": p.price,
            "image_url": absolute_image_url(filename),
            "artisan": {
                "id": p.artisan.id,
                "name": p.artisan.name,
                "location": p.artisan.location,
                "contact_number": p.artisan.contact_number,
                "bio": p.artisan.bio_translated,
            },
        })
    return results

@app.get("/image/{product_id}")
def get_image(product_id: int):
    """
    Legacy endpoint for compatibility; prefer using the absolute image_url from APIs.
    """
    db: Session = next(get_db())
    p = db.query(Product).get(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    path = MEDIA_DIR / Path(p.image_path).name
    return safe_fileresponse(path)

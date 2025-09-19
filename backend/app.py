# backend/app.py
import os
import io
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Load .env early
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import SessionLocal, engine, Base
from .models import Artisan, Product
from .utils import save_image_and_enhance, translate_and_enrich

# Debug GEMINI key presence
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    print("✅ GEMINI_API_KEY loaded from environment.")
else:
    print("⚠️ GEMINI_API_KEY not found. Gemini calls may be skipped.")

# Create tables if DB empty
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Artisan Prototype API")
app.state.gemini_key = GEMINI_API_KEY

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "🚀 Artisan Prototype API is running", "gemini_loaded": bool(app.state.gemini_key)}

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

# DB session helper
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/register_artisan")
def register_artisan(
    name: str = Form(...),
    location: str = Form(...),
    language: str = Form("English"),
    bio: str = Form(""),
    contact_number: str = Form("")   # <-- accept contact_number from frontend
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
        bio_enriched=enriched_bio
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
    # build product list
    products = []
    for p in artisan.products:
        products.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "image_url": f"/image/{p.id}"
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
        "products": products
    }

@app.put("/artisan/{artisan_id}")
def update_artisan(artisan_id: int, name: str = Form(None), location: str = Form(None), language: str = Form(None), bio: str = Form(None), contact_number: str = Form(None)):
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
        # translate/enrich again (optional) — keep original behavior
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
    file: UploadFile = File(...)
):
    path = save_image_and_enhance(file)
    db: Session = next(get_db())
    # ensure artisan exists
    art = db.query(Artisan).get(artisan_id)
    if not art:
        raise HTTPException(status_code=404, detail="Artisan not found")
    product = Product(artisan_id=artisan_id, name=product_name, description=description, price=price, image_path=str(path))
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"id": product.id, "image": product.image_path}

@app.put("/product/{product_id}")
async def update_product(product_id: int, product_name: str = Form(None), description: str = Form(None), price: str = Form(None), file: UploadFile = File(None)):
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
        # replace image
        path = save_image_and_enhance(file)
        p.image_path = str(path)
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
            "language": a.language
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
        results.append({
            "product_id": p.id,
            "name": p.name,
            "price": p.price,
            "image_url": f"/image/{p.id}",
            "artisan": {
                "id": p.artisan.id,
                "name": p.artisan.name,
                "location": p.artisan.location,
                "contact_number": p.artisan.contact_number,   # <-- include contact in search results
                "bio": p.artisan.bio_translated
            }
        })
    return results

@app.get("/image/{product_id}")
def get_image(product_id: int):
    db: Session = next(get_db())
    p = db.query(Product).get(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return FileResponse(p.image_path)


# scripts/fix_paths.py
from pathlib import Path
from backend.db import SessionLocal
from backend.models import Product

db = SessionLocal()
for p in db.query(Product).all():
    p.image_path = Path(p.image_path).name
db.commit()
db.close()

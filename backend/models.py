# backend/models.py
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base

class Artisan(Base):
    __tablename__ = "artisans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    location = Column(String, index=True)
    language = Column(String, default="English")
    contact_number = Column(String, index=True)            # <-- NEW: store 10-digit contact
    bio_original = Column(Text)
    bio_translated = Column(Text)
    bio_enriched = Column(Text)
    products = relationship("Product", back_populates="artisan")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    artisan_id = Column(Integer, ForeignKey("artisans.id"))
    name = Column(String, index=True)
    description = Column(Text)
    price = Column(String)
    image_path = Column(String)
    artisan = relationship("Artisan", back_populates="products")

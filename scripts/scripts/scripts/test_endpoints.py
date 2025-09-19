# scripts/test_endpoints.py
import requests
from PIL import Image, ImageDraw
import io
import os
import sys
import time

BACKEND = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

def register_artisan(name="Test Artisan", location="Testville", language="English", bio="This is a test artisan."):
    print("Registering artisan...")
    resp = requests.post(f"{BACKEND}/register_artisan", data={
        "name": name, "location": location, "language": language, "bio": bio
    })
    print("Status:", resp.status_code)
    print(resp.text)
    resp.raise_for_status()
    return resp.json().get("id")

def create_sample_image_bytes(text="sample"):
    img = Image.new("RGB", (800, 600), color=(240,240,240))
    d = ImageDraw.Draw(img)
    d.text((20,20), text, fill=(10,10,10))
    b = io.BytesIO()
    img.save(b, format="JPEG")
    b.seek(0)
    return b

def upload_product(artisan_id, product_name="Sample Product", price="100"):
    print("Uploading product...")
    b = create_sample_image_bytes(product_name)
    files = {"file": ("sample.jpg", b, "image/jpeg")}
    data = {"artisan_id": artisan_id, "product_name": product_name, "description": "Automated test upload", "price": price}
    resp = requests.post(f"{BACKEND}/upload_product", data=data, files=files)
    print("Status:", resp.status_code)
    print(resp.text)
    resp.raise_for_status()
    return resp.json()

def search(q="Sample", location="Testville"):
    print("Searching...")
    resp = requests.get(f"{BACKEND}/search", params={"q": q, "location": location})
    print("Status:", resp.status_code)
    print(resp.text)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    try:
        artisan_id = register_artisan(name="Auto Tester", location="Testville", language="English", bio="Auto test bio")
        time.sleep(1)
        up = upload_product(artisan_id, product_name="Auto Pot", price="250")
        time.sleep(1)
        results = search(q="Auto", location="Testville")
        print("Search returned:", results)
        print("Automated test completed successfully.")
    except Exception as e:
        print("Error during automated test:", e)
        sys.exit(1)

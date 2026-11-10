import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("OPENAQ_API_KEY")
print("loaded, length:", len(key) if key else None)
import os

# Allow accidental Settings() imports in tests without a real .env. Never used to connect.
os.environ.setdefault("MONGO_URI", "mongodb://invalid.invalid:27017")

from beanie.odm.settings.document import DocumentSettings

from app.modules.standards.models import Standard

# Beanie Document.__init__ requires initialized collection settings. Tests never
# call init_beanie (no Mongo); this dummy only lets us construct entities for the dict fake.
Standard._document_settings = DocumentSettings(name="standards")

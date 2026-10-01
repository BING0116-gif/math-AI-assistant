"""Report note storage drift without changing files or database records."""
import asyncio
import json
from app.services.note_cleanup import reconcile_note_storage

if __name__ == "__main__":
    print(json.dumps(asyncio.run(reconcile_note_storage()), ensure_ascii=False, indent=2))

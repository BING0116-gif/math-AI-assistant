"""Import seed questions from Excel to database and vector store."""
import asyncio
import sys
sys.path.insert(0, '.')

from app.data.database import init_db, close_db
from app.services.question_importer import QuestionImporter
from app.services.vector_store import get_vector_store


async def import_questions():
    await init_db()
    vs = await get_vector_store()
    importer = QuestionImporter(vector_store=vs)
    result = await importer.import_from_excel('data/seed_questions.xlsx')
    print(f"Total: {result.total}, Success: {result.success}, Failed: {result.failed}")
    print(f"Imported IDs: {result.imported_ids}")
    if result.errors:
        print(f"Errors: {result.errors[:5]}")

    # Verify
    stats = await vs.get_collection_stats()
    print(f"Vector store stats: {stats}")


asyncio.run(import_questions())
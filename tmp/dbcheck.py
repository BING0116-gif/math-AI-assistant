import asyncio,sys,os
sys.path.insert(0,os.getcwd())
from app.data.database import init_db,get_db_session,close_db
from sqlalchemy import select,func
from app.data.models import Question
async def x():
 await init_db()
 async with get_db_session() as db: print('questions',await db.scalar(select(func.count()).select_from(Question)))
 await close_db()
asyncio.run(x())

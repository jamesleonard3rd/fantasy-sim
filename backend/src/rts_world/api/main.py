from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..db.db import get_connection

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"Hello", "World"}

@app.get("/entities")
def list_entities():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, type FROM entities ORDER BY id LIMIT 100")
            rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "type": r[2]} for r in rows]
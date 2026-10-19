from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import agent, projects, recycle_bin, story_memory, users
from config.db_conf import init_db, close_db
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(title="神笔小说创作 API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(users.router)
# Register legacy project URLs before the parameterized project routes so
# paths such as /api/project/restoreProject are not parsed as integer IDs.
app.include_router(recycle_bin.legacy_router)
app.include_router(projects.router)
app.include_router(agent.router)
app.include_router(story_memory.router)
app.include_router(recycle_bin.router)

@app.get("/")
async def root():
    return {"message": "Hello World"}


# @app.get("/hello/{name}")
# async def say_hello(name: str):
#     return {"message": f"Hello {name}"}

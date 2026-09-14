from fastapi import FastAPI
from app.routers import leads, ingest, ai_assist
from fastapi.staticfiles import StaticFiles

app = FastAPI(title = "Lead Management API")
app.include_router(leads.router, prefix="/api", tags=["Leads"])
app.include_router(ingest.router, prefix="/api", tags=["Ingest"])
app.include_router(ai_assist.router, prefix="/api", tags=["AI Assisted"])
app.mount("/", StaticFiles(directory="/frontend", html=True), name="frontend")
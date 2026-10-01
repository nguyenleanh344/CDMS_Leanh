from fastapi import FastAPI
from app.api import emulator, webhook, sync, imports

app = FastAPI(title="CDMS Handson Emulator Service")

app.include_router(emulator.router)
app.include_router(webhook.router)
app.include_router(sync.router)
app.include_router(imports.router)
@app.get("/health")
def health_check():
    return {"Status": "Ok"}
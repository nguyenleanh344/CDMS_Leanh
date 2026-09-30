from fastapi import FastAPI
from app.api import emulator

app = FastAPI(title="CDMS Handson Emulator Service")

app.include_router(emulator.router)

@app.get("/health")
def health_check():
    return {"Status": "Ok"}
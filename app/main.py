from fastapi import FastAPI

app = FastAPI(title="Performance Layer API")

@app.get("/health")
def health():
    return {"status": "ok"}
from fastapi import FastAPI
from .routes.files import router as files_router


app = FastAPI(title="AES-256-CBC File Encryption API")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


app.include_router(files_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


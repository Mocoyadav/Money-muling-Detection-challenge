from io import StringIO
from typing import Any, Dict

import pandas as pd
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from detector import detect_all_patterns

app = FastAPI(title="Money Muling Detection")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def index() -> Any:
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file.",
        )
    try:
        content_bytes = await file.read()
        csv_text = content_bytes.decode("utf-8")
        df = pd.read_csv(StringIO(csv_text))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse CSV: {exc}",
        ) from exc

    required_cols = {
        "transaction_id",
        "sender_id",
        "receiver_id",
        "amount",
        "timestamp",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(sorted(missing))}",
        )

    result = detect_all_patterns(df)
    return JSONResponse(result)


app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

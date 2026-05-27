from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os

from database import engine, get_db, Base
from models import Shot

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Espresso Log")
app.mount("/static", StaticFiles(directory="public"), name="static")


# ── Schemas ───────────────────────────────────────────────────────────────────

class ShotIn(BaseModel):
    roast: str
    grind_size: float
    dose_g: float
    yield_g: float
    time_s: int
    rating: int
    tasting_notes: Optional[str] = ""
    notes: Optional[str] = ""

class ShotOut(BaseModel):
    id: int
    timestamp: datetime
    roast: str
    grind_size: float
    dose_g: float
    yield_g: float
    time_s: int
    rating: int
    tasting_notes: str
    notes: str
    ratio: Optional[float]

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse("public/index.html")

@app.post("/shots", response_model=ShotOut)
def log_shot(shot: ShotIn, db: Session = Depends(get_db)):
    row = Shot(**shot.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@app.get("/shots", response_model=list[ShotOut])
def list_shots(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Shot).order_by(Shot.timestamp.desc()).limit(limit).all()

@app.get("/shots/{shot_id}", response_model=ShotOut)
def get_shot(shot_id: int, db: Session = Depends(get_db)):
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    return shot

@app.delete("/shots/{shot_id}")
def delete_shot(shot_id: int, db: Session = Depends(get_db)):
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    db.delete(shot)
    db.commit()
    return {"ok": True}

@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    total = db.query(func.count(Shot.id)).scalar()
    if total == 0:
        return {"total": 0}

    avg_rating = db.query(func.avg(Shot.rating)).scalar()
    avg_time   = db.query(func.avg(Shot.time_s)).scalar()
    avg_dose   = db.query(func.avg(Shot.dose_g)).scalar()
    avg_yield  = db.query(func.avg(Shot.yield_g)).scalar()

    best = (
        db.query(Shot)
        .filter(Shot.rating == db.query(func.max(Shot.rating)).scalar())
        .order_by(Shot.timestamp.desc())
        .first()
    )

    return {
        "total": total,
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "avg_time_s": round(avg_time, 1) if avg_time else None,
        "avg_dose_g": round(avg_dose, 1) if avg_dose else None,
        "avg_yield_g": round(avg_yield, 1) if avg_yield else None,
        "best_shot": ShotOut.model_validate(best) if best else None,
    }

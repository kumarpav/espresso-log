from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
import anthropic

from database import engine, get_db, Base
from models import Shot

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Espresso Coach")
app.mount("/static", StaticFiles(directory="public"), name="static")

_anthropic = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

COACH_SYSTEM_PROMPT = """\
You are a friendly, encouraging espresso coach helping new home baristas pull better shots.
You understand the key variables: grind size, dose, yield, extraction time, and how they
interact. Your job is to read a shot log and give clear, specific, beginner-friendly advice
on what to adjust next time.

Key espresso principles to draw on:
- Ideal extraction time: 25–35 seconds. Too fast = under-extracted (sour, thin). Too slow = over-extracted (bitter, harsh).
- Ideal ratio: 1:2 to 1:2.5 for classic espresso. Higher ratio = lighter/more acidic. Lower = stronger/more bitter.
- Grind finer → slower flow → more body, more risk of bitterness.
- Grind coarser → faster flow → brighter/sourer, less body.
- Sour or acidic taste → usually under-extracted → grind finer, or reduce yield.
- Bitter or harsh taste → usually over-extracted → grind coarser, or increase yield.
- Weak or watery → reduce yield (stop pulling earlier).
- Astringent or dry → grind coarser, check puck prep.

If previous shots for the same roast are provided, reference them explicitly — acknowledge
what changed and whether it helped, and build on that trajectory.

Always give 2–3 numbered, specific adjustments. Mention the direction and a rough magnitude
where possible (e.g. "try going 0.5 clicks finer"). Explain briefly why each change helps.
End with one sentence of encouragement. Keep total response under 200 words."""


def generate_advice(shot: Shot, prev_shots: list) -> str:
    ratio = f"1:{shot.ratio}" if shot.ratio else "unknown"
    time_note = (
        "under-extracted (too fast)" if shot.time_s < 25 else
        "over-extracted (too slow)" if shot.time_s > 35 else
        "within ideal range"
    )

    history = ""
    if prev_shots:
        history = "\n\nPrevious shots with this same roast (oldest → newest):\n"
        for ps in reversed(prev_shots):
            history += (
                f"- Grind {ps.grind_size}, {ps.dose_g}g→{ps.yield_g}g, "
                f"{ps.time_s}s, rated {ps.rating}/5"
            )
            if ps.tasting_notes:
                history += f': "{ps.tasting_notes}"'
            history += "\n"

    user_msg = f"""Current shot:
- Roast: {shot.roast}
- Dose: {shot.dose_g}g in → {shot.yield_g}g out (ratio {ratio})
- Extraction time: {shot.time_s}s ({time_note})
- Grind size: {shot.grind_size}
- Rating: {shot.rating}/5
- Tasting notes: {shot.tasting_notes or 'none provided'}
- Additional notes: {shot.notes or 'none'}{history}

What should I adjust for my next shot?"""

    try:
        response = _anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=[{
                "type": "text",
                "text": COACH_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }],
            messages=[{"role": "user", "content": user_msg}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        return response.content[0].text
    except Exception:
        return ""


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
    advice: str
    ratio: Optional[float]

    class Config:
        from_attributes = True

class RoastSummary(BaseModel):
    roast: str
    count: int
    avg_rating: float
    best_shot: Optional[ShotOut]
    shots: list[ShotOut]


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
    prev = (
        db.query(Shot)
        .filter(Shot.roast == row.roast, Shot.id != row.id)
        .order_by(Shot.timestamp.desc())
        .limit(3)
        .all()
    )
    row.advice = generate_advice(row, prev)
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

@app.get("/roasts", response_model=list[RoastSummary])
def list_roasts(db: Session = Depends(get_db)):
    roast_names = (
        db.query(Shot.roast)
        .group_by(Shot.roast)
        .order_by(func.max(Shot.timestamp).desc())
        .all()
    )
    result = []
    for (roast,) in roast_names:
        shots = (
            db.query(Shot)
            .filter(Shot.roast == roast)
            .order_by(Shot.timestamp.desc())
            .all()
        )
        avg_rating = sum(s.rating for s in shots) / len(shots)
        best = max(shots, key=lambda s: (s.rating, s.timestamp))
        result.append(RoastSummary(
            roast=roast,
            count=len(shots),
            avg_rating=round(avg_rating, 1),
            best_shot=ShotOut.model_validate(best),
            shots=[ShotOut.model_validate(s) for s in shots],
        ))
    return result

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

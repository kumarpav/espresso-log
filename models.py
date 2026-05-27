from sqlalchemy import Column, Integer, Float, String, Text, DateTime
from datetime import datetime, timezone
from database import Base

class Shot(Base):
    __tablename__ = "shots"

    id          = Column(Integer, primary_key=True, index=True)
    timestamp   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    roast       = Column(String(120))
    grind_size  = Column(Float)
    dose_g      = Column(Float)   # input grams
    yield_g     = Column(Float)   # output grams
    time_s      = Column(Integer) # extraction seconds
    rating      = Column(Integer) # 1–5
    tasting_notes = Column(Text, default="")
    notes       = Column(Text, default="")

    @property
    def ratio(self):
        if self.dose_g and self.dose_g > 0:
            return round(self.yield_g / self.dose_g, 2)
        return None

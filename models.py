from sqlalchemy import Column, Integer, Float, String, Text, DateTime
from datetime import datetime, timezone
from database import Base

class Shot(Base):
    __tablename__ = "shots"

    id            = Column(Integer, primary_key=True, index=True)
    timestamp     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    token         = Column(String(64), index=True, default="", server_default="")
    roast         = Column(String(120))
    grind_size    = Column(Float)
    dose_g        = Column(Float)
    yield_g       = Column(Float)
    time_s        = Column(Integer)
    rating        = Column(Integer)
    tasting_notes = Column(Text, default="")
    notes         = Column(Text, default="")
    advice        = Column(Text, default="")

    @property
    def ratio(self):
        if self.dose_g and self.dose_g > 0:
            return round(self.yield_g / self.dose_g, 2)
        return None


class Recipe(Base):
    __tablename__ = "recipes"

    id         = Column(Integer, primary_key=True, index=True)
    token      = Column(String(64), index=True, default="", server_default="")
    name       = Column(String(120))
    roast      = Column(String(120))
    grind_size = Column(Float)
    dose_g     = Column(Float)
    yield_g    = Column(Float)
    time_s     = Column(Integer)
    notes      = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    shot_id    = Column(Integer, nullable=True)

    @property
    def ratio(self):
        if self.dose_g and self.dose_g > 0:
            return round(self.yield_g / self.dose_g, 2)
        return None


class UserConfig(Base):
    __tablename__ = "user_config"

    id    = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), index=True, default="")
    key   = Column(String(50))
    value = Column(Text)


# Legacy table — kept so existing DB doesn't error on startup
class Config(Base):
    __tablename__ = "config"
    key   = Column(String(50), primary_key=True)
    value = Column(Text)

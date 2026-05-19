from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base


class ScrapingJob(Base):
    __tablename__ = "scraping_jobs"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    total      = Column(Integer, nullable=False, default=0)
    pending    = Column(Integer, nullable=False, default=0)
    running    = Column(Integer, nullable=False, default=0)
    completed  = Column(Integer, nullable=False, default=0)
    failed     = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user  = relationship("User")
    tasks = relationship("ScrapingTask", back_populates="job", cascade="all, delete-orphan")


class ScrapingTask(Base):
    __tablename__ = "scraping_tasks"

    id           = Column(Integer, primary_key=True, index=True)
    job_id       = Column(Integer, ForeignKey("scraping_jobs.id"), nullable=False)
    asin         = Column(String(20), nullable=False)
    status       = Column(String(20), nullable=False, default="pending")  # pending/running/completed/failed
    error        = Column(Text, nullable=True)
    queued_at    = Column(DateTime, default=datetime.utcnow)
    started_at   = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    job     = relationship("ScrapingJob", back_populates="tasks")
    product = relationship("ProductData", back_populates="task", uselist=False, cascade="all, delete-orphan")


class ProductData(Base):
    __tablename__ = "product_data"

    id           = Column(Integer, primary_key=True, index=True)
    task_id      = Column(Integer, ForeignKey("scraping_tasks.id"), nullable=False, unique=True)
    asin         = Column(String(20), nullable=False)
    title        = Column(Text, nullable=True)
    brand        = Column(String(255), nullable=True)
    price        = Column(String(50), nullable=True)
    rating       = Column(String(10), nullable=True)
    review_count = Column(String(50), nullable=True)
    availability = Column(String(200), nullable=True)
    image_url    = Column(Text, nullable=True)
    scraped_at   = Column(DateTime, default=datetime.utcnow)

    task = relationship("ScrapingTask", back_populates="product")

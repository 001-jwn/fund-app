"""SQLite tables for Milestone 1. Column types are portable to PostgreSQL."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class Company(Base):
    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255))
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_change_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Nullable on purpose. Milestone 1 never fills or displays this.
    holder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_news_headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_news_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_news_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quarterly_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_quarter_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    data_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CompanyInterest(Base):
    __tablename__ = "company_interests"

    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), primary_key=True)
    interest: Mapped[str] = mapped_column(String(32), primary_key=True)
    why_line: Mapped[str] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserInterest(Base):
    __tablename__ = "user_interests"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    interest: Mapped[str] = mapped_column(String(32), primary_key=True)


class Like(Base):
    __tablename__ = "likes"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Dislike(Base):
    __tablename__ = "dislikes"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Match(Base):
    __tablename__ = "matches"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

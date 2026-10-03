"""SQLAlchemy models. Monetary values are GBP floats (2dp on output)."""
from __future__ import annotations

from datetime import datetime, date
from typing import Any, Optional

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Niche(Base):
    __tablename__ = "niches"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # search terms, hints, checklist, postage classes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    search_queries: Mapped[list["SearchQuery"]] = relationship(back_populates="niche", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))  # api | browser | paid
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok|paused|needs_login|blocked|error|disabled
    status_message: Mapped[str] = mapped_column(Text, default="")
    poll_interval_min: Mapped[int] = mapped_column(Integer, default=15)
    max_page_loads_per_hour: Mapped[int] = mapped_column(Integer, default=40)
    min_delay_s: Mapped[int] = mapped_column(Integer, default=45)
    max_delay_s: Mapped[int] = mapped_column(Integer, default=120)
    quiet_hours: Mapped[str] = mapped_column(String(16), default="23-07")
    buyer_fee_pct: Mapped[float] = mapped_column(Float, default=0.0)   # e.g. Vinted buyer protection %
    buyer_fee_fixed: Mapped[float] = mapped_column(Float, default=0.0)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    page_loads_window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    page_loads_in_window: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class SearchQuery(Base):
    __tablename__ = "search_queries"
    id: Mapped[int] = mapped_column(primary_key=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id"), nullable=True)  # null = all sources
    query: Mapped[str] = mapped_column(String(200))
    filters: Mapped[dict] = mapped_column(JSON, default=dict)  # max_price, category etc.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    niche: Mapped[Niche] = relationship(back_populates="search_queries")


class RawListing(Base):
    __tablename__ = "raw_listings"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_external"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    external_id: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    listing_type: Mapped[str] = mapped_column(String(16), default="bin")  # bin | auction
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    postage_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # None = unknown
    collection_only: Mapped[bool] = mapped_column(Boolean, default=False)
    location_text: Mapped[str] = mapped_column(String(128), default="")
    postcode_district: Mapped[str] = mapped_column(String(8), default="")
    seller_name: Mapped[str] = mapped_column(String(128), default="")   # personal data: purged after retention
    seller_feedback: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_urls: Mapped[list] = mapped_column(JSON, default=list)
    image_hash: Mapped[str] = mapped_column(String(32), default="")
    condition_text: Mapped[str] = mapped_column(String(64), default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new|processed|duplicate|error|purged
    duplicate_of_id: Mapped[Optional[int]] = mapped_column(ForeignKey("raw_listings.id"), nullable=True)

    source: Mapped[Source] = relationship()
    niche: Mapped[Niche] = relationship()


class NormalisedItem(Base):
    __tablename__ = "normalised_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    raw_listing_id: Mapped[int] = mapped_column(ForeignKey("raw_listings.id"))
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    platform: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    region: Mapped[str] = mapped_column(String(16), default="")      # PAL | NTSC-U | NTSC-J | unknown
    completeness: Mapped[str] = mapped_column(String(16), default="")  # loose|boxed|cib|sealed|graded
    condition_notes: Mapped[str] = mapped_column(Text, default="")
    is_bundle: Mapped[bool] = mapped_column(Boolean, default=False)
    bundle_items: Mapped[list] = mapped_column(JSON, default=list)   # [{platform,title,completeness}]
    console_model: Mapped[str] = mapped_column(String(64), default="")
    accessories: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(32), default="game")  # game|console|accessory|bundle
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)      # [{code,label,severity,detail}]
    item_key: Mapped[str] = mapped_column(String(64), index=True)      # cache key: platform|title|region|completeness
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    model_name: Mapped[str] = mapped_column(String(64), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    raw_listing: Mapped[RawListing] = relationship()


class Valuation(Base):
    __tablename__ = "valuations"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_key: Mapped[str] = mapped_column(String(64), index=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    median_price: Mapped[float] = mapped_column(Float, default=0.0)
    p25: Mapped[float] = mapped_column(Float, default=0.0)
    p75: Mapped[float] = mapped_column(Float, default=0.0)
    sold_count: Mapped[int] = mapped_column(Integer, default=0)
    active_count: Mapped[int] = mapped_column(Integer, default=0)
    sell_through_rate: Mapped[float] = mapped_column(Float, default=0.0)
    est_days_to_sell: Mapped[int] = mapped_column(Integer, default=999)
    confidence: Mapped[str] = mapped_column(String(8), default="low")  # low|medium|high
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    providers: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SoldComp(Base):
    __tablename__ = "sold_comps"
    __table_args__ = (Index("ix_sold_comps_lookup", "niche_id", "platform", "region", "completeness"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    provider: Mapped[str] = mapped_column(String(32))  # ebay_insights | csv | own_sales | mock
    external_id: Mapped[str] = mapped_column(String(128), default="")
    platform: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(16), default="")
    completeness: Mapped[str] = mapped_column(String(16), default="")
    sold_price: Mapped[float] = mapped_column(Float)
    postage: Mapped[float] = mapped_column(Float, default=0.0)
    sold_at: Mapped[datetime] = mapped_column(DateTime)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[int] = mapped_column(primary_key=True)
    raw_listing_id: Mapped[int] = mapped_column(ForeignKey("raw_listings.id"), unique=True)
    normalised_item_id: Mapped[int] = mapped_column(ForeignKey("normalised_items.id"))
    valuation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("valuations.id"), nullable=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    buy_price: Mapped[float] = mapped_column(Float)
    buyer_fees: Mapped[float] = mapped_column(Float, default=0.0)
    inbound_cost: Mapped[float] = mapped_column(Float, default=0.0)   # postage or collection cost
    landed_cost: Mapped[float] = mapped_column(Float, default=0.0)
    expected_sale_price: Mapped[float] = mapped_column(Float, default=0.0)
    sell_fees: Mapped[float] = mapped_column(Float, default=0.0)
    outbound_postage: Mapped[float] = mapped_column(Float, default=0.0)
    packaging: Mapped[float] = mapped_column(Float, default=0.0)
    reserve: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    net_margin: Mapped[float] = mapped_column(Float, default=0.0)  # fraction 0-1
    roi: Mapped[float] = mapped_column(Float, default=0.0)
    est_days_to_sell: Mapped[int] = mapped_column(Integer, default=999)
    tier: Mapped[str] = mapped_column(String(16), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    distance_miles: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    collection_only: Mapped[bool] = mapped_column(Boolean, default=False)
    check_manually: Mapped[bool] = mapped_column(Boolean, default=False)
    capital_warning: Mapped[bool] = mapped_column(Boolean, default=False)
    should_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    skip_reason: Mapped[str] = mapped_column(String(200), default="")
    priority: Mapped[str] = mapped_column(String(8), default="low")  # high|default|low
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new|alerted|bought|passed|watching|expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    raw_listing: Mapped[RawListing] = relationship()
    item: Mapped[NormalisedItem] = relationship()
    valuation: Mapped[Optional[Valuation]] = relationship()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="deal")  # deal|digest|daily|source|task
    channel: Mapped[str] = mapped_column(String(16), default="mock")
    priority: Mapped[str] = mapped_column(String(8), default="default")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|sent|failed|digested
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    deal: Mapped[Optional[Deal]] = relationship()


INVENTORY_STATUSES = ["in_transit", "testing", "ready_to_photograph", "listed", "sold", "shipped", "returned"]


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    deal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deals.id"), nullable=True)
    normalised_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("normalised_items.id"), nullable=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    title: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(32), default="game")
    completeness: Mapped[str] = mapped_column(String(16), default="")
    region: Mapped[str] = mapped_column(String(16), default="")
    source: Mapped[str] = mapped_column(String(32), default="")
    cost_basis: Mapped[float] = mapped_column(Float)         # landed cost
    purchase_price: Mapped[float] = mapped_column(Float, default=0.0)
    purchase_date: Mapped[date] = mapped_column(Date, default=date.today)
    status: Mapped[str] = mapped_column(String(24), default="in_transit")
    expected_sale_price: Mapped[float] = mapped_column(Float, default=0.0)
    expected_days_to_sell: Mapped[int] = mapped_column(Integer, default=30)
    expected_net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    weight_class: Mapped[str] = mapped_column(String(32), default="small_parcel")
    listed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    deal: Mapped[Optional[Deal]] = relationship()
    test_results: Mapped[list["TestResult"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    listings: Mapped[list["Listing"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    sales: Mapped[list["Sale"]] = relationship(back_populates="item", cascade="all, delete-orphan")

    @property
    def expected_sell_by(self) -> Optional[date]:
        base = self.listed_at.date() if self.listed_at else self.purchase_date
        from datetime import timedelta
        return base + timedelta(days=self.expected_days_to_sell)

    @property
    def is_overdue(self) -> bool:
        return self.status in ("listed",) and self.expected_sell_by is not None and date.today() > self.expected_sell_by


class TestResult(Base):
    __tablename__ = "test_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    checklist: Mapped[list] = mapped_column(JSON, default=list)  # [{key,label,result,notes}]
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    grade: Mapped[str] = mapped_column(String(16), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    tested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    item: Mapped[InventoryItem] = relationship(back_populates="test_results")


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    title: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    condition_description: Mapped[str] = mapped_column(Text, default="")
    item_specifics: Mapped[dict] = mapped_column(JSON, default=dict)
    price: Mapped[float] = mapped_column(Float)
    markdown_schedule: Mapped[list] = mapped_column(JSON, default=list)  # [{day, price}]
    photo_shot_list: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|active|sold|ended
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    item: Mapped[InventoryItem] = relationship(back_populates="listings")
    platform_listings: Mapped[list["PlatformListing"]] = relationship(back_populates="listing", cascade="all, delete-orphan")


class PlatformListing(Base):
    __tablename__ = "platform_listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    platform: Mapped[str] = mapped_column(String(32))  # ebay | vinted | ...
    external_id: Mapped[str] = mapped_column(String(128), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|ended|sold|remove_pending
    listed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    listing: Mapped[Listing] = relationship(back_populates="platform_listings")


class Sale(Base):
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    platform: Mapped[str] = mapped_column(String(32))
    external_order_id: Mapped[str] = mapped_column(String(128), default="")
    sale_price: Mapped[float] = mapped_column(Float)
    postage_charged: Mapped[float] = mapped_column(Float, default=0.0)
    platform_fees: Mapped[float] = mapped_column(Float, default=0.0)
    payment_fees: Mapped[float] = mapped_column(Float, default=0.0)
    postage_cost: Mapped[float] = mapped_column(Float, default=0.0)
    packaging_cost: Mapped[float] = mapped_column(Float, default=0.0)
    other_costs: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    net_margin: Mapped[float] = mapped_column(Float, default=0.0)
    days_to_sell: Mapped[int] = mapped_column(Integer, default=0)
    sold_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | ebay_fulfilment

    item: Mapped[InventoryItem] = relationship(back_populates="sales")


class FeeConfig(Base):
    __tablename__ = "fee_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    group: Mapped[str] = mapped_column(String(32))     # buy_fees | sell_fees | payment | costs | travel
    label: Mapped[str] = mapped_column(String(128))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(8))       # pct | gbp | gbp_per_mile | gbp_per_hour | mph
    last_verified: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    verify_flag: Mapped[bool] = mapped_column(Boolean, default=True)  # True = "VERIFY" (default not checked by you)
    notes: Mapped[str] = mapped_column(Text, default="")


class PostageRate(Base):
    __tablename__ = "postage_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    carrier: Mapped[str] = mapped_column(String(32))
    service: Mapped[str] = mapped_column(String(64))
    weight_class: Mapped[str] = mapped_column(String(32))  # large_letter|small_parcel|medium_parcel|...
    max_weight_g: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    default_for_class: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    verify_flag: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CapitalLedger(Base):
    __tablename__ = "capital_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_type: Mapped[str] = mapped_column(String(16))  # deposit|purchase|sale|fee|adjust|withdraw
    amount: Mapped[float] = mapped_column(Float)         # +ve inflow, -ve outflow
    balance_after: Mapped[float] = mapped_column(Float)
    ref_type: Mapped[str] = mapped_column(String(32), default="")
    ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Insight(Base):
    __tablename__ = "insights"
    id: Mapped[int] = mapped_column(primary_key=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    content_md: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    ready_to_clone: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Task(Base):
    """Urgent to-dos surfaced in the dashboard (e.g. 'remove from other platforms')."""
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    ref_type: Mapped[str] = mapped_column(String(32), default="")
    ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

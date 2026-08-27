import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from salla_ghl.db.session import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class EventStatus(str, enum.Enum):
    received = "received"
    queued = "queued"
    processing = "processing"
    processed = "processed"
    ignored = "ignored"
    failed = "failed"


class WorkflowStatus(str, enum.Enum):
    scheduled = "scheduled"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class OutboundStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    retrying = "retrying"


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    source: Mapped[str] = mapped_column(String(40), default="salla")
    merchant_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.received, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SallaIntegration(Base):
    __tablename__ = "salla_integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    store_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    store_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    salla_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ghl_contact_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="new")
    total_spent: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    purchase_count: Mapped[int] = mapped_column(Integer, default=0)
    last_purchase_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    tags: Mapped[list["CustomerTag"]] = relationship(back_populates="customer")
    product_interests: Mapped[list["ProductInterest"]] = relationship(back_populates="customer")

    __table_args__ = (
        Index("ix_customers_identity", "email", "phone"),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    salla_order_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    payment_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fulfillment_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="SAR")
    admin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    customer: Mapped[Customer | None] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    salla_product_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    order: Mapped[Order] = relationship(back_populates="items")


class CustomerTag(Base):
    __tablename__ = "customer_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    tag: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="salla")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="tags")

    __table_args__ = (UniqueConstraint("customer_id", "tag", name="uq_customer_tag"),)


class ProductInterest(Base):
    __tablename__ = "product_interests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    salla_product_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="salla")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="product_interests")

    __table_args__ = (
        UniqueConstraint("customer_id", "salla_product_id", "sku", name="uq_customer_product_interest"),
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    workflow_type: Mapped[str] = mapped_column(String(120), index=True)
    stage: Mapped[str] = mapped_column(String(120), default="initial")
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.scheduled)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class OutboundRequest(Base):
    __tablename__ = "outbound_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(60), default="ghl")
    method: Mapped[str] = mapped_column(String(20), default="POST")
    url: Mapped[str] = mapped_column(Text)
    request_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OutboundStatus] = mapped_column(Enum(OutboundStatus), default=OutboundStatus.pending, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class GHLEventDelivery(Base):
    __tablename__ = "ghl_event_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    request_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OutboundStatus] = mapped_column(Enum(OutboundStatus), default=OutboundStatus.pending, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_name: Mapped[str] = mapped_column(String(120), unique=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(80), default="idle")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

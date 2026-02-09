"""Pydantic schemas for API."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


class MessageRequest(BaseModel):
    """Request to send a message."""
    channel: str = Field(..., description="Channel name", min_length=1, max_length=20)
    body: str = Field(..., description="Message body", min_length=1, max_length=1000)
    priority: int = Field(default=1, ge=0, le=3, description="Priority (0=highest, 3=lowest)")
    reply_to: Optional[str] = Field(default=None, description="Message ID being replied to")
    author: Optional[str] = Field(default=None, description="Session nickname (transient)")

    @field_validator('channel')
    @classmethod
    def validate_channel(cls, v):
        """Ensure channel is lowercase ASCII."""
        if not v.islower() or not v.isascii():
            raise ValueError("Channel must be lowercase ASCII")
        return v


class MessageResponse(BaseModel):
    """Response containing a message."""
    id: str = Field(..., description="Message ID")
    from_node: str = Field(..., description="Sender callsign")
    author: Optional[str] = Field(default=None, description="Sender nickname from web UI (transient)")
    timestamp: str = Field(..., description="Message timestamp")
    channel: str = Field(..., description="Channel name")
    priority: int = Field(..., description="Priority level")
    reply_to: Optional[str] = Field(default=None, description="Reply to message ID")
    body: str = Field(..., description="Message body")
    received_at: datetime = Field(..., description="When message was received")
    transmitted_at: Optional[datetime] = Field(default=None, description="When transmitted")



class NodeResponse(BaseModel):
    """Response containing node information."""
    callsign: str = Field(..., description="Node callsign")
    first_seen: datetime = Field(..., description="First activity")
    last_seen: datetime = Field(..., description="Last activity")
    last_sync: Optional[datetime] = Field(default=None, description="Last SYNC frame")
    message_count: int = Field(..., description="Total messages")
    sync_count: int = Field(..., description="Total SYNC frames")
    req_count: int = Field(..., description="Total REQ frames")



class ChannelResponse(BaseModel):
    """Response containing channel information."""
    name: str = Field(..., description="Channel name")
    first_message: datetime = Field(..., description="First message time")
    last_message: datetime = Field(..., description="Last message time")
    message_count: int = Field(..., description="Total messages")
    unique_nodes: int = Field(..., description="Unique nodes")



class StatusResponse(BaseModel):
    """Response containing daemon status."""
    version: str = Field(..., description="Daemon version")
    uptime_seconds: float = Field(..., description="Uptime in seconds")
    connected_to_direwolf: bool = Field(..., description="Direwolf connection status")
    node_callsign: str = Field(..., description="Local node callsign")
    stats: dict = Field(..., description="Various statistics")


class ErrorResponse(BaseModel):
    """Error response."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(default=None, description="Detailed error information")


class CallsignRequest(BaseModel):
    """Request to update callsign."""
    callsign: str = Field(..., description="Amateur radio callsign", min_length=1, max_length=6)
    ssid: int = Field(default=0, ge=0, le=15, description="SSID (0-15)")

    @field_validator('callsign')
    @classmethod
    def validate_callsign(cls, v):
        """Validate callsign format."""
        v = v.upper()
        if not v.replace('-', '').isalnum():
            raise ValueError("Callsign must be alphanumeric")
        return v
"""
Communication Channels Integration
==================================
Manages communication channels for incident response:
- Slack (channels, DMs, threads, workflows)
- Zoom (war rooms, breakout rooms)
- PagerDuty (on-call, escalations, notifications)
- Status Page (public/private status updates)
- Email (stakeholder communications)
- Webhooks (custom integrations)
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import logging
import uuid

logger = logging.getLogger(__name__)


class ChannelType(Enum):
    """Types of communication channels."""
    SLACK = "slack"
    ZOOM = "zoom"
    PAGERDUTY = "pagerduty"
    STATUS_PAGE = "status_page"
    EMAIL = "email"
    WEBHOOK = "webhook"
    TEAMS = "teams"
    DISCORD = "discord"
    SMS = "sms"
    PHONE = "phone"


class ChannelPurpose(Enum):
    """Purpose of a communication channel in incident response."""
    WAR_ROOM = "war_room"                 # Main incident coordination
    BREAKOUT = "breakout"                 # Technical deep-dive
    COMMUNICATIONS = "communications"     # Stakeholder updates
    EXECUTIVE = "executive"               # Executive briefings
    CUSTOMER = "customer"                 # Customer-facing updates
    ONCALL = "oncall"                     # On-call coordination
    POSTMORTEM = "postmortem"             # Post-incident review
    GENERAL = "general"                   # General discussion


class MessagePriority(Enum):
    """Message priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


@dataclass
class ChannelConfig:
    """Configuration for a communication channel."""
    channel_id: str
    name: str
    channel_type: ChannelType
    purpose: ChannelPurpose

    # Connection details
    credentials: Dict[str, str] = field(default_factory=dict)  # tokens, keys, etc.
    endpoint: str = ""

    # Channel-specific settings
    settings: Dict[str, Any] = field(default_factory=dict)

    # Access control
    allowed_roles: List[str] = field(default_factory=list)
    allowed_users: List[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """A message to be sent to a channel."""
    id: str = field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    channel_id: str = ""
    content: str = ""
    priority: MessagePriority = MessagePriority.NORMAL
    sender: str = "system"
    sender_role: str = ""

    # Formatting
    blocks: List[Dict[str, Any]] = field(default_factory=list)  # Slack blocks, etc.
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    thread_ts: str = ""  # For threaded replies

    # Metadata
    incident_id: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    delivery_status: str = "pending"  # pending, sent, delivered, failed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "content": self.content,
            "priority": self.priority.value,
            "sender": self.sender,
            "sender_role": self.sender_role,
            "blocks": self.blocks,
            "attachments": self.attachments,
            "thread_ts": self.thread_ts,
            "incident_id": self.incident_id,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivery_status": self.delivery_status
        }


@dataclass
class WarRoom:
    """Represents an incident war room with multiple channels."""
    id: str
    incident_id: str
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""

    # Channels
    channels: Dict[str, ChannelConfig] = field(default_factory=dict)  # purpose -> channel

    # Participants
    participants: List[str] = field(default_factory=list)
    roles: Dict[str, str] = field(default_factory=dict)  # user -> role

    # Settings
    is_active: bool = True
    auto_archive_hours: int = 24

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(ABC):
    """Abstract base class for channel adapters."""

    @abstractmethod
    def send_message(self, channel: ChannelConfig, message: Message) -> bool:
        """Send a message to the channel."""
        pass

    @abstractmethod
    def create_channel(self, config: ChannelConfig) -> Optional[ChannelConfig]:
        """Create a new channel."""
        pass

    @abstractmethod
    def archive_channel(self, channel: ChannelConfig) -> bool:
        """Archive a channel."""
        pass

    @abstractmethod
    def invite_users(self, channel: ChannelConfig, users: List[str]) -> bool:
        """Invite users to channel."""
        pass

    @abstractmethod
    def get_channel_info(self, channel: ChannelConfig) -> Dict[str, Any]:
        """Get channel information."""
        pass


class SlackAdapter(ChannelAdapter):
    """Slack channel adapter."""

    def __init__(self, bot_token: str = "", app_token: str = "", signing_secret: str = ""):
        self.bot_token = bot_token
        self.app_token = app_token
        self.signing_secret = signing_secret
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Slack client."""
        try:
            from slack_sdk import WebClient
            from slack_sdk.errors import SlackApiError
            self.client = WebClient(token=self.bot_token)
            self.SlackApiError = SlackApiError
        except ImportError:
            logger.warning("slack_sdk not installed. Slack adapter will use mock mode.")
            self.client = None

    def send_message(self, channel: ChannelConfig, message: Message) -> bool:
        """Send message to Slack channel."""
        if not self.client:
            return self._mock_send(channel, message)

        try:
            kwargs = {
                "channel": channel.settings.get("channel_id", channel.channel_id),
                "text": message.content,
            }

            if message.blocks:
                kwargs["blocks"] = json.dumps(message.blocks)
            if message.attachments:
                kwargs["attachments"] = json.dumps(message.attachments)
            if message.thread_ts:
                kwargs["thread_ts"] = message.thread_ts
            if message.priority in [MessagePriority.HIGH, MessagePriority.URGENT, MessagePriority.CRITICAL]:
                kwargs["icon_emoji"] = ":rotating_light:"

            response = self.client.chat_postMessage(**kwargs)
            message.sent_at = datetime.utcnow()
            message.delivery_status = "sent"
            message.metadata["slack_ts"] = response.get("ts")
            return True

        except self.SlackApiError as e:
            logger.error(f"Slack send failed: {e}")
            message.delivery_status = "failed"
            return False

    def create_channel(self, config: ChannelConfig) -> Optional[ChannelConfig]:
        """Create a Slack channel."""
        if not self.client:
            return self._mock_create(config)

        try:
            channel_name = config.name.lower().replace(" ", "-")
            is_private = config.settings.get("private", False)

            response = self.client.conversations_create(
                name=channel_name,
                is_private=is_private
            )

            channel_info = response["channel"]
            config.channel_id = channel_info["id"]
            config.settings["channel_id"] = channel_info["id"]
            config.endpoint = f"https://slack.com/app_redirect?channel={channel_info['id']}"

            # Set topic/purpose
            if config.settings.get("topic"):
                self.client.conversations_setTopic(
                    channel=channel_info["id"],
                    topic=config.settings["topic"]
                )
            if config.settings.get("purpose"):
                self.client.conversations_setPurpose(
                    channel=channel_info["id"],
                    purpose=config.settings["purpose"]
                )

            return config

        except self.SlackApiError as e:
            logger.error(f"Slack channel create failed: {e}")
            return None

    def archive_channel(self, channel: ChannelConfig) -> bool:
        """Archive a Slack channel."""
        if not self.client:
            return True

        try:
            self.client.conversations_archive(channel=channel.settings.get("channel_id", channel.channel_id))
            return True
        except self.SlackApiError as e:
            logger.error(f"Slack archive failed: {e}")
            return False

    def invite_users(self, channel: ChannelConfig, users: List[str]) -> bool:
        """Invite users to Slack channel."""
        if not self.client:
            return True

        try:
            channel_id = channel.settings.get("channel_id", channel.channel_id)
            for user in users:
                self.client.conversations_invite(channel=channel_id, users=[user])
            return True
        except self.SlackApiError as e:
            logger.error(f"Slack invite failed: {e}")
            return False

    def get_channel_info(self, channel: ChannelConfig) -> Dict[str, Any]:
        """Get Slack channel info."""
        if not self.client:
            return {"mock": True, "channel_id": channel.channel_id}

        try:
            response = self.client.conversations_info(channel=channel.settings.get("channel_id", channel.channel_id))
            return response["channel"]
        except self.SlackApiError as e:
            logger.error(f"Slack get info failed: {e}")
            return {}

    def _mock_send(self, channel: ChannelConfig, message: Message) -> bool:
        """Mock send for testing."""
        print(f"[MOCK SLACK -> {channel.name}] {message.content[:100]}...")
        message.sent_at = datetime.utcnow()
        message.delivery_status = "sent"
        return True

    def _mock_create(self, config: ChannelConfig) -> ChannelConfig:
        """Mock channel creation."""
        config.channel_id = f"C{uuid.uuid4().hex[:8].upper()}"
        config.settings["channel_id"] = config.channel_id
        return config

    def create_incident_thread(self, channel: ChannelConfig, incident_id: str, title: str, details: str) -> str:
        """Create an incident thread in Slack."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🚨 Incident: {title}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Incident ID:*\n{incident_id}"},
                    {"type": "mrkdwn", "text": f"*Status:*\nInvestigating"},
                    {"type": "mrkdwn", "text": f"*Created:*\n{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"},
                    {"type": "mrkdwn", "text": f"*Channel:*\n{channel.name}"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Details:*\n{details}"}
            },
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Acknowledge"}, "style": "primary", "value": f"ack_{incident_id}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Escalate"}, "style": "danger", "value": f"esc_{incident_id}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Runbook"}, "value": f"rb_{incident_id}"}
                ]
            }
        ]

        message = Message(
            channel_id=channel.channel_id,
            content=f"Incident {incident_id}: {title}",
            blocks=blocks,
            priority=MessagePriority.HIGH,
            incident_id=incident_id
        )

        self.send_message(channel, message)
        return message.metadata.get("slack_ts", "")


class ZoomAdapter(ChannelAdapter):
    """Zoom channel adapter for war rooms."""

    def __init__(self, account_id: str = "", client_id: str = "", client_secret: str = ""):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = ""
        self.token_expires = datetime.min

    def _get_token(self) -> str:
        """Get OAuth token for Zoom API."""
        if datetime.utcnow() < self.token_expires and self.access_token:
            return self.access_token

        # In production, implement JWT or OAuth flow
        # This is a placeholder
        self.access_token = "mock_token"
        self.token_expires = datetime.utcnow() + timedelta(hours=1)
        return self.access_token

    def send_message(self, channel: ChannelConfig, message: Message) -> bool:
        """Send message to Zoom chat (in-meeting or channel)."""
        # Zoom chat API would go here
        print(f"[MOCK ZOOM -> {channel.name}] {message.content[:100]}...")
        message.sent_at = datetime.utcnow()
        message.delivery_status = "sent"
        return True

    def create_channel(self, config: ChannelConfig) -> Optional[ChannelConfig]:
        """Create a Zoom meeting for war room."""
        meeting_id = f"{uuid.uuid4().hex[:10]}"
        config.channel_id = meeting_id
        config.endpoint = f"https://zoom.us/j/{meeting_id}"
        config.settings["meeting_id"] = meeting_id
        config.settings["join_url"] = config.endpoint
        config.settings["password"] = uuid.uuid4().hex[:6]
        return config

    def create_war_room_meeting(self, incident_id: str, title: str, duration_minutes: int = 120) -> Dict[str, Any]:
        """Create a Zoom war room meeting."""
        meeting = {
            "topic": f"War Room: {title} ({incident_id})",
            "type": 2,  # Scheduled meeting
            "start_time": datetime.utcnow().isoformat() + "Z",
            "duration": duration_minutes,
            "timezone": "UTC",
            "settings": {
                "host_video": True,
                "participant_video": True,
                "join_before_host": True,
                "mute_upon_entry": True,
                "waiting_room": False,
                "allow_multiple_devices": True,
                "recording": True,
                "auto_recording": "cloud"
            }
        }

        # In production, call Zoom API
        meeting_id = f"{uuid.uuid4().hex[:10]}"
        meeting["id"] = meeting_id
        meeting["join_url"] = f"https://zoom.us/j/{meeting_id}"
        meeting["password"] = uuid.uuid4().hex[:6]

        return meeting

    def create_breakout_rooms(self, meeting_id: str, rooms: List[Dict[str, Any]]) -> bool:
        """Create breakout rooms for technical deep-dives."""
        # Zoom breakout room API
        print(f"[MOCK ZOOM] Creating {len(rooms)} breakout rooms for meeting {meeting_id}")
        return True

    def archive_channel(self, channel: ChannelConfig) -> bool:
        """End Zoom meeting."""
        print(f"[MOCK ZOOM] Ending meeting {channel.channel_id}")
        return True

    def invite_users(self, channel: ChannelConfig, users: List[str]) -> bool:
        """Invite users to Zoom meeting (send calendar invites)."""
        print(f"[MOCK ZOOM] Inviting {users} to meeting {channel.channel_id}")
        return True

    def get_channel_info(self, channel: ChannelConfig) -> Dict[str, Any]:
        """Get Zoom meeting info."""
        return {
            "id": channel.channel_id,
            "join_url": channel.settings.get("join_url"),
            "topic": channel.name
        }


class PagerDutyAdapter(ChannelAdapter):
    """PagerDuty adapter for on-call management and alerting."""

    def __init__(self, api_key: str = "", subdomain: str = ""):
        self.api_key = api_key
        self.subdomain = subdomain
        self.base_url = f"https://{subdomain}.pagerduty.com/api/v1" if subdomain else "https://api.pagerduty.com"

    def send_message(self, channel: ChannelConfig, message: Message) -> bool:
        """Trigger a PagerDuty incident or send a note."""
        # PagerDuty Events API v2
        print(f"[MOCK PAGERDUTY -> {channel.name}] {message.content[:100]}...")
        message.sent_at = datetime.utcnow()
        message.delivery_status = "sent"
        return True

    def trigger_incident(
        self,
        summary: str,
        severity: str = "critical",
        source: str = "ai-sre",
        component: str = "",
        group: str = "",
        class_type: str = "",
        custom_details: Dict = None,
        routing_key: str = ""
    ) -> str:
        """Trigger a PagerDuty incident."""
        incident_key = f"inc-{uuid.uuid4().hex[:8]}"
        print(f"[MOCK PAGERDUTY] Triggered incident: {summary} (key: {incident_key})")
        return incident_key

    def acknowledge_incident(self, incident_key: str, user: str) -> bool:
        """Acknowledge a PagerDuty incident."""
        print(f"[MOCK PAGERDUTY] Incident {incident_key} acknowledged by {user}")
        return True

    def resolve_incident(self, incident_key: str, user: str) -> bool:
        """Resolve a PagerDuty incident."""
        print(f"[MOCK PAGERDUTY] Incident {incident_key} resolved by {user}")
        return True

    def escalate_incident(self, incident_key: str, escalation_policy_id: str) -> bool:
        """Manually escalate an incident."""
        print(f"[MOCK PAGERDUTY] Escalating incident {incident_key} via policy {escalation_policy_id}")
        return True

    def get_on_call(self, schedule_id: str) -> Dict[str, Any]:
        """Get current on-call for a schedule."""
        return {
            "user": "oncall-user",
            "email": "oncall@company.com",
            "schedule_id": schedule_id,
            "start": datetime.utcnow().isoformat(),
            "end": (datetime.utcnow() + timedelta(hours=12)).isoformat()
        }

    def create_channel(self, config: ChannelConfig) -> Optional[ChannelConfig]:
        """Create a PagerDuty service/integration."""
        config.channel_id = f"SV{uuid.uuid4().hex[:6].upper()}"
        return config

    def archive_channel(self, channel: ChannelConfig) -> bool:
        return True

    def invite_users(self, channel: ChannelConfig, users: List[str]) -> bool:
        return True

    def get_channel_info(self, channel: ChannelConfig) -> Dict[str, Any]:
        return {"id": channel.channel_id, "type": "pagerduty_service"}


class StatusPageAdapter(ChannelAdapter):
    """Status page adapter (e.g., Atlassian Statuspage, PagerDuty Status Pages)."""

    def __init__(self, api_key: str = "", page_id: str = "", provider: str = "statuspage"):
        self.api_key = api_key
        self.page_id = page_id
        self.provider = provider

    def send_message(self, channel: ChannelConfig, message: Message) -> bool:
        """Post update to status page."""
        print(f"[MOCK STATUSPAGE -> {channel.name}] {message.content[:100]}...")
        message.sent_at = datetime.utcnow()
        message.delivery_status = "sent"
        return True

    def create_incident(
        self,
        name: str,
        status: str = "investigating",
        impact: str = "minor",
        components: List[str] = None,
        body: str = "",
        metadata: Dict = None
    ) -> str:
        """Create a status page incident."""
        incident_id = f"spi-{uuid.uuid4().hex[:8]}"
        print(f"[MOCK STATUSPAGE] Created incident: {name} (ID: {incident_id}, Status: {status})")
        return incident_id

    def update_incident(
        self,
        incident_id: str,
        status: str = None,
        body: str = None,
        impact: str = None,
        components: List[str] = None
    ) -> bool:
        """Update a status page incident."""
        print(f"[MOCK STATUSPAGE] Updated incident {incident_id}: status={status}, impact={impact}")
        return True

    def resolve_incident(self, incident_id: str, body: str = "") -> bool:
        """Resolve a status page incident."""
        print(f"[MOCK STATUSPAGE] Resolved incident {incident_id}")
        return True

    def post_maintenance(
        self,
        name: str,
        scheduled_for: datetime,
        scheduled_until: datetime,
        status: str = "scheduled",
        components: List[str] = None,
        body: str = ""
    ) -> str:
        """Post scheduled maintenance."""
        maintenance_id = f"spm-{uuid.uuid4().hex[:8]}"
        print(f"[MOCK STATUSPAGE] Scheduled maintenance: {name}")
        return maintenance_id

    def create_channel(self, config: ChannelConfig) -> Optional[ChannelConfig]:
        return config

    def archive_channel(self, channel: ChannelConfig) -> bool:
        return True

    def invite_users(self, channel: ChannelConfig, users: List[str]) -> bool:
        return True

    def get_channel_info(self, channel: ChannelConfig) -> Dict[str, Any]:
        return {"page_id": self.page_id, "provider": self.provider}


class EmailAdapter(ChannelAdapter):
    """Email adapter for stakeholder communications."""

    def __init__(self, smtp_host: str = "", smtp_port: int = 587, username: str = "", password: str = "", from_email: str = ""):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email

    def send_message(self, channel: ChannelConfig, message: Message) -> bool:
        """Send email."""
        recipients = channel.settings.get("recipients", [])
        subject = message.blocks[0].get("text", message.content[:80]) if message.blocks else message.content[:80]

        print(f"[MOCK EMAIL -> {recipients}] Subject: {subject}")
        print(f"  Body: {message.content[:200]}...")
        message.sent_at = datetime.utcnow()
        message.delivery_status = "sent"
        return True

    def send_incident_notification(
        self,
        incident_id: str,
        title: str,
        severity: str,
        recipients: List[str],
        details: str,
        action_required: bool = False
    ) -> bool:
        """Send formatted incident notification email."""
        subject = f"[{severity}] Incident {incident_id}: {title}"
        body = f"""
Incident Notification
=====================

Incident ID: {incident_id}
Title: {title}
Severity: {severity}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

Details:
{details}

{"⚠️ ACTION REQUIRED" if action_required else "For awareness only."}

---
This is an automated message from the AI SRE Incident Management System.
"""

        channel = ChannelConfig(
            channel_id="email-notifications",
            name="Email Notifications",
            channel_type=ChannelType.EMAIL,
            purpose=ChannelType.COMMUNICATIONS,
            settings={"recipients": recipients}
        )

        message = Message(
            channel_id=channel.channel_id,
            content=body,
            priority=MessagePriority.HIGH if action_required else MessagePriority.NORMAL,
            incident_id=incident_id,
            blocks=[{"text": subject}]
        )

        return self.send_message(channel, message)

    def create_channel(self, config: ChannelConfig) -> Optional[ChannelConfig]:
        return config

    def archive_channel(self, channel: ChannelConfig) -> bool:
        return True

    def invite_users(self, channel: ChannelConfig, users: List[str]) -> bool:
        return True

    def get_channel_info(self, channel: ChannelConfig) -> Dict[str, Any]:
        return {"type": "email", "from": self.from_email}


class WebhookAdapter(ChannelAdapter):
    """Generic webhook adapter for custom integrations."""

    def __init__(self, default_url: str = "", default_headers: Dict = None):
        self.default_url = default_url
        self.default_headers = default_headers or {"Content-Type": "application/json"}

    def send_message(self, channel: ChannelConfig, message: Message) -> bool:
        """Send webhook."""
        url = channel.settings.get("webhook_url", self.default_url)
        headers = {**self.default_headers, **channel.settings.get("headers", {})}
        payload = message.to_dict()

        print(f"[MOCK WEBHOOK -> {url}] {json.dumps(payload)[:200]}...")
        message.sent_at = datetime.utcnow()
        message.delivery_status = "sent"
        return True

    def create_channel(self, config: ChannelConfig) -> Optional[ChannelConfig]:
        return config

    def archive_channel(self, channel: ChannelConfig) -> bool:
        return True

    def invite_users(self, channel: ChannelConfig, users: List[str]) -> bool:
        return True

    def get_channel_info(self, channel: ChannelConfig) -> Dict[str, Any]:
        return {"type": "webhook", "url": channel.settings.get("webhook_url")}


class CommunicationManager:
    """Central manager for all communication channels."""

    def __init__(self):
        self.adapters: Dict[ChannelType, ChannelAdapter] = {}
        self.channels: Dict[str, ChannelConfig] = {}
        self.war_rooms: Dict[str, WarRoom] = {}
        self.message_history: List[Message] = []

    def register_adapter(self, channel_type: ChannelType, adapter: ChannelAdapter) -> None:
        """Register a channel adapter."""
        self.adapters[channel_type] = adapter
        logger.info(f"Registered adapter for {channel_type.value}")

    def add_channel(self, config: ChannelConfig) -> None:
        """Add a channel configuration."""
        self.channels[config.channel_id] = config

    def get_channel(self, channel_id: str) -> Optional[ChannelConfig]:
        """Get channel by ID."""
        return self.channels.get(channel_id)

    def send_message(self, channel_id: str, message: Message) -> bool:
        """Send a message to a channel."""
        channel = self.channels.get(channel_id)
        if not channel:
            logger.error(f"Channel not found: {channel_id}")
            return False

        adapter = self.adapters.get(channel.channel_type)
        if not adapter:
            logger.error(f"No adapter for channel type: {channel.channel_type}")
            return False

        message.channel_id = channel_id
        success = adapter.send_message(channel, message)

        # Record in history
        self.message_history.append(message)

        return success

    def broadcast(
        self,
        message: Message,
        channel_types: List[ChannelType] = None,
        purposes: List[ChannelPurpose] = None,
        severity_filter: str = None
    ) -> Dict[str, bool]:
        """Broadcast message to multiple channels."""
        results = {}

        for channel in self.channels.values():
            if not channel.is_active:
                continue

            if channel_types and channel.channel_type not in channel_types:
                continue

            if purposes and channel.purpose not in purposes:
                continue

            if severity_filter and message.priority.value != severity_filter:
                continue

            # Create copy for each channel
            msg_copy = Message(
                channel_id=channel.channel_id,
                content=message.content,
                priority=message.priority,
                sender=message.sender,
                sender_role=message.sender_role,
                blocks=message.blocks.copy(),
                attachments=message.attachments.copy(),
                incident_id=message.incident_id,
                tags=message.tags.copy()
            )

            results[channel.channel_id] = self.send_message(channel.channel_id, msg_copy)

        return results

    def create_war_room(
        self,
        incident_id: str,
        title: str,
        created_by: str,
        channel_configs: List[Dict[str, Any]] = None
    ) -> WarRoom:
        """Create a war room with multiple channels."""
        war_room = WarRoom(
            id=f"wr-{incident_id}",
            incident_id=incident_id,
            name=f"War Room: {title}",
            created_by=created_by
        )

        # Default channel configurations
        default_configs = [
            {
                "purpose": ChannelPurpose.WAR_ROOM,
                "type": ChannelType.SLACK,
                "name": f"incident-{incident_id}",
                "settings": {"topic": f"Incident {incident_id}: {title}", "purpose": "Main war room coordination"}
            },
            {
                "purpose": ChannelPurpose.BREAKOUT,
                "type": ChannelType.SLACK,
                "name": f"incident-{incident_id}-breakout",
                "settings": {"topic": "Technical deep-dive", "purpose": "Technical investigation"}
            },
            {
                "purpose": ChannelPurpose.COMMUNICATIONS,
                "type": ChannelType.SLACK,
                "name": f"incident-{incident-id}-comms",
                "settings": {"topic": "Stakeholder communications", "purpose": "Status updates"}
            },
            {
                "purpose": ChannelPurpose.WAR_ROOM,
                "type": ChannelType.ZOOM,
                "name": f"War Room: {title}",
                "settings": {}
            }
        ]

        configs = channel_configs or default_configs

        for cfg in configs:
            channel = ChannelConfig(
                channel_id=f"{war_room.id}-{cfg['purpose'].value}",
                name=cfg["name"],
                channel_type=cfg["type"],
                purpose=cfg["purpose"],
                settings=cfg.get("settings", {})
            )

            adapter = self.adapters.get(channel.channel_type)
            if adapter:
                created = adapter.create_channel(channel)
                if created:
                    war_room.channels[cfg["purpose"].value] = created
                    self.add_channel(created)

        self.war_rooms[war_room.id] = war_room
        return war_room

    def get_war_room(self, incident_id: str) -> Optional[WarRoom]:
        """Get war room for incident."""
        return self.war_rooms.get(f"wr-{incident_id}")

    def add_participant(self, war_room_id: str, user: str, role: str = "") -> bool:
        """Add participant to war room."""
        war_room = self.war_rooms.get(war_room_id)
        if not war_room:
            return False

        if user not in war_room.participants:
            war_room.participants.append(user)
            if role:
                war_room.roles[user] = role

            # Invite to all channels
            for channel in war_room.channels.values():
                adapter = self.adapters.get(channel.channel_type)
                if adapter:
                    adapter.invite_users(channel, [user])

        return True

    def post_incident_update(
        self,
        incident_id: str,
        title: str,
        status: str,
        details: str,
        severity: str = "SEV-2",
        audiences: List[ChannelPurpose] = None
    ) -> Dict[str, bool]:
        """Post incident update to appropriate channels."""
        audiences = audiences or [
            ChannelPurpose.WAR_ROOM,
            ChannelPurpose.COMMUNICATIONS,
            ChannelPurpose.EXECUTIVE
        ]

        # Determine priority from severity
        priority_map = {
            "SEV-1": MessagePriority.CRITICAL,
            "SEV-2": MessagePriority.HIGH,
            "SEV-3": MessagePriority.NORMAL,
            "SEV-4": MessagePriority.LOW
        }

        # Build message
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📋 Incident Update: {title}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Incident ID:*\n{incident_id}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{status}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                    {"type": "mrkdwn", "text": f"*Updated:*\n{datetime.utcnow().strftime('%H:%M UTC')}"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Update:*\n{details}"}
            }
        ]

        message = Message(
            content=f"Incident {incident_id} Update: {status}",
            priority=priority_map.get(severity, MessagePriority.NORMAL),
            sender="Incident Commander",
            sender_role="INCIDENT_COMMANDER",
            blocks=blocks,
            incident_id=incident_id,
            tags=["update", status.lower()]
        )

        return self.broadcast(message, purposes=audiences)

    def send_executive_briefing(
        self,
        incident_id: str,
        title: str,
        severity: str,
        summary: str,
        impact: str,
        next_steps: List[str],
        eta: str = ""
    ) -> bool:
        """Send executive briefing."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📊 Executive Briefing: {title}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Incident:*\n{incident_id}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                    {"type": "mrkdwn", "text": f"*Impact:*\n{impact}"},
                    {"type": "mrkdwn", "text": f"*ETA:*\n{eta or 'TBD'}"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Next Steps:*\n" + "\n".join(f"• {step}" for step in next_steps)}
            }
        ]

        message = Message(
            content=f"Executive Briefing: {title}",
            priority=MessagePriority.HIGH,
            sender="Incident Commander",
            sender_role="INCIDENT_COMMANDER",
            blocks=blocks,
            incident_id=incident_id,
            tags=["executive", "briefing"]
        )

        results = self.broadcast(message, purposes=[ChannelPurpose.EXECUTIVE])
        return any(results.values())

    def archive_war_room(self, incident_id: str) -> bool:
        """Archive war room after incident resolution."""
        war_room = self.get_war_room(incident_id)
        if not war_room:
            return False

        war_room.is_active = False

        for channel in war_room.channels.values():
            adapter = self.adapters.get(channel.channel_type)
            if adapter:
                adapter.archive_channel(channel)

        return True

    def get_message_history(self, incident_id: str = None, channel_id: str = None, limit: int = 100) -> List[Message]:
        """Get message history."""
        messages = self.message_history

        if incident_id:
            messages = [m for m in messages if m.incident_id == incident_id]
        if channel_id:
            messages = [m for m in messages if m.channel_id == channel_id]

        return sorted(messages, key=lambda m: m.created_at, reverse=True)[:limit]


def create_communication_manager(config: Dict[str, Any] = None) -> CommunicationManager:
    """Create a configured communication manager."""
    manager = CommunicationManager()
    config = config or {}

    # Register Slack adapter
    slack_config = config.get("slack", {})
    slack_adapter = SlackAdapter(
        bot_token=slack_config.get("bot_token", ""),
        app_token=slack_config.get("app_token", ""),
        signing_secret=slack_config.get("signing_secret", "")
    )
    manager.register_adapter(ChannelType.SLACK, slack_adapter)

    # Register Zoom adapter
    zoom_config = config.get("zoom", {})
    zoom_adapter = ZoomAdapter(
        account_id=zoom_config.get("account_id", ""),
        client_id=zoom_config.get("client_id", ""),
        client_secret=zoom_config.get("client_secret", "")
    )
    manager.register_adapter(ChannelType.ZOOM, zoom_adapter)

    # Register PagerDuty adapter
    pd_config = config.get("pagerduty", {})
    pd_adapter = PagerDutyAdapter(
        api_key=pd_config.get("api_key", ""),
        subdomain=pd_config.get("subdomain", "")
    )
    manager.register_adapter(ChannelType.PAGERDUTY, pd_adapter)

    # Register Status Page adapter
    sp_config = config.get("status_page", {})
    sp_adapter = StatusPageAdapter(
        api_key=sp_config.get("api_key", ""),
        page_id=sp_config.get("page_id", ""),
        provider=sp_config.get("provider", "statuspage")
    )
    manager.register_adapter(ChannelType.STATUS_PAGE, sp_adapter)

    # Register Email adapter
    email_config = config.get("email", {})
    email_adapter = EmailAdapter(
        smtp_host=email_config.get("smtp_host", ""),
        smtp_port=email_config.get("smtp_port", 587),
        username=email_config.get("username", ""),
        password=email_config.get("password", ""),
        from_email=email_config.get("from_email", "")
    )
    manager.register_adapter(ChannelType.EMAIL, email_adapter)

    # Register Webhook adapter
    webhook_config = config.get("webhook", {})
    webhook_adapter = WebhookAdapter(
        default_url=webhook_config.get("default_url", ""),
        default_headers=webhook_config.get("default_headers", {})
    )
    manager.register_adapter(ChannelType.WEBHOOK, webhook_adapter)

    return manager


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    # Create manager
    manager = create_communication_manager({
        "slack": {"bot_token": "xoxb-mock"},
        "zoom": {},
        "pagerduty": {"subdomain": "company"},
        "status_page": {"page_id": "status.company.com"},
        "email": {"from_email": "incidents@company.com"}
    })

    # Create war room
    print("=== Creating War Room ===")
    war_room = manager.create_war_room(
        incident_id="INC-2024-001",
        title="Payment Service Outage",
        created_by="incident-commander"
    )
    print(f"War room created: {war_room.id}")
    print(f"Channels: {list(war_room.channels.keys())}")

    # Add participants
    print("\n=== Adding Participants ===")
    for user, role in [("alice", "INCIDENT_COMMANDER"), ("bob", "TECH_LEAD"), ("carol", "SRE_LEAD")]:
        manager.add_participant(war_room.id, user, role)
        print(f"  Added {user} as {role}")

    # Post incident update
    print("\n=== Posting Incident Update ===")
    results = manager.post_incident_update(
        incident_id="INC-2024-001",
        title="Payment Service Outage",
        status="investigating",
        details="Identified latency spike in payment-api. Investigating database connection pool exhaustion.",
        severity="SEV-1",
        audiences=[ChannelPurpose.WAR_ROOM, ChannelPurpose.COMMUNICATIONS, ChannelPurpose.EXECUTIVE]
    )
    print(f"Broadcast results: {results}")

    # Send executive briefing
    print("\n=== Sending Executive Briefing ===")
    success = manager.send_executive_briefing(
        incident_id="INC-2024-001",
        title="Payment Service Outage",
        severity="SEV-1",
        summary="Payment service experiencing 100% error rate due to database connection pool exhaustion. All payment processing halted.",
        impact="Revenue impact: ~$50k/min. All customer payments failing.",
        next_steps=[
            "Scale database read replicas",
            "Increase connection pool limits",
            "Implement circuit breaker for non-critical queries",
            "Monitor recovery"
        ],
        eta="30 minutes"
    )
    print(f"Executive briefing sent: {success}")

    # Trigger PagerDuty
    print("\n=== Triggering PagerDuty ===")
    pd_adapter = manager.adapters[ChannelType.PAGERDUTY]
    incident_key = pd_adapter.trigger_incident(
        summary="Payment Service Outage - SEV-1",
        severity="critical",
        component="payment-api",
        custom_details={"incident_id": "INC-2024-001", "war_room": war_room.id}
    )
    print(f"PagerDuty incident key: {incident_key}")

    # Create status page incident
    print("\n=== Creating Status Page Incident ===")
    sp_adapter = manager.adapters[ChannelType.STATUS_PAGE]
    sp_incident = sp_adapter.create_incident(
        name="Payment Service Degraded Performance",
        status="investigating",
        impact="major",
        components=["payment-api", "checkout"],
        body="We are investigating reports of payment processing failures."
    )
    print(f"Status page incident: {sp_incident}")

    # Message history
    print("\n=== Message History ===")
    history = manager.get_message_history(incident_id="INC-2024-001")
    for msg in history:
        print(f"  [{msg.channel_id}] {msg.content[:80]}...")
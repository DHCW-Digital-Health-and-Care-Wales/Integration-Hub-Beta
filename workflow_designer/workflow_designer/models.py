from dataclasses import dataclass, field


@dataclass
class SubscriptionSenderDefinition:
    """One subscription sender destination in an MPI outbound / subscription flow."""

    health_board: str
    peer_service: str
    workflow_id: str
    receiver_host: str
    receiver_port: int = 2576
    ack_timeout_seconds: int = 5
    max_messages_per_minute: int = 30

    @property
    def slug(self) -> str:
        """Lowercase kebab slug for resource naming, e.g. mpi-sww → mpi_sww."""
        return self.health_board.lower().replace("-", "_")

    @property
    def subscription_name_ref(self) -> str:
        """TF local reference for the subscription name."""
        return f"local.servicebus_subscription_{self.slug}_sender_name"


@dataclass
class MpiOutboundFlowDefinition:
    """Subscription-based MPI outbound flow (topic fan-out pattern)."""

    flow_id: str
    source_system: str
    mllp_port: int
    hl7_version: str
    sending_app: str
    validation_flow: str
    health_board: str
    enable_message_store: bool = True
    subscription_senders: list[SubscriptionSenderDefinition] = field(default_factory=list)
    readonly: bool = False

    @property
    def flow_var_name(self) -> str:
        return self.flow_id.replace("-", "_")

    @property
    def source_slug(self) -> str:
        return self.source_system.lower()

    @property
    def pattern(self) -> str:
        return "Subscription Fan-out"


@dataclass
class FlowDefinition:
    flow_id: str
    source_system: str
    mllp_port: int
    hl7_version: str
    sending_app: str
    validation_flow: str
    health_board: str
    destination: str = "MPI"
    has_transformer: bool = False
    transformer_image_name: str = ""
    has_dedicated_sender: bool = False
    destination_host: str = ""
    destination_port: int = 2576
    enable_message_store: bool = True
    readonly: bool = False

    @property
    def flow_var_name(self) -> str:
        """Underscore version for TF variable/local names e.g. phw_to_mpi."""
        return self.flow_id.replace("-", "_")

    @property
    def source_slug(self) -> str:
        """Lowercase source system for image tags e.g. phw."""
        return self.source_system.lower()

    @property
    def pattern(self) -> str:
        """Return pattern label for display."""
        if not self.has_transformer:
            return "Direct (no transformer)"
        if self.has_dedicated_sender:
            return "Transform + Dedicated Sender"
        return "Transform + Shared Sender"

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "flow_id": self.flow_id,
            "source_system": self.source_system,
            "mllp_port": self.mllp_port,
            "hl7_version": self.hl7_version,
            "sending_app": self.sending_app,
            "validation_flow": self.validation_flow,
            "health_board": self.health_board,
            "destination": self.destination,
            "has_transformer": self.has_transformer,
            "transformer_image_name": self.transformer_image_name,
            "has_dedicated_sender": self.has_dedicated_sender,
            "destination_host": self.destination_host,
            "destination_port": self.destination_port,
            "enable_message_store": self.enable_message_store,
            "readonly": self.readonly,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | int | bool]) -> "FlowDefinition":
        return cls(
            flow_id=str(data["flow_id"]),
            source_system=str(data["source_system"]),
            mllp_port=int(data["mllp_port"]),
            hl7_version=str(data["hl7_version"]),
            sending_app=str(data["sending_app"]),
            validation_flow=str(data["validation_flow"]),
            health_board=str(data["health_board"]),
            destination=str(data.get("destination", "MPI")),
            has_transformer=bool(data.get("has_transformer", False)),
            transformer_image_name=str(data.get("transformer_image_name", "")),
            has_dedicated_sender=bool(data.get("has_dedicated_sender", False)),
            destination_host=str(data.get("destination_host", "")),
            destination_port=int(data.get("destination_port", 2576)),
            enable_message_store=bool(data.get("enable_message_store", True)),
            readonly=bool(data.get("readonly", False)),
        )

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionConfig:
    connection_string: str | None
    service_bus_namespace: str | None

    def is_using_connection_string(self) -> bool:
        return bool(self.connection_string and self.connection_string.strip())

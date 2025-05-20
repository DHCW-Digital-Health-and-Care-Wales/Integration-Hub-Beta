from dataclasses import dataclass

@dataclass(frozen=True)
class ConnectionConfig:
    connection_string: str
    service_bus_namespace: str

    def is_using_connection_string(self) -> bool:
        return bool(self.connection_string and self.connection_string.strip())
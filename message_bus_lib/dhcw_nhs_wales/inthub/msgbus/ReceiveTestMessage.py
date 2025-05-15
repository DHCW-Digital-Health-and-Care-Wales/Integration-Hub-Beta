import os
from ConnectionConfig import ConnectionConfig
from ServiceBusClientFactory import ServiceBusClientFactory

def process_message(message):
    body_bytes = b''.join(message.body)
    print(f"Received message: {body_bytes.decode('utf-8')}")
    print(f"Properties: {message.application_properties}")
    return {"success": True}

def main():
    connection_config = ConnectionConfig(
        connection_string="Endpoint=sb://127.0.0.1;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;",
        service_bus_namespace=""
    )

    client_factory = ServiceBusClientFactory(connection_config)

    try:
        receiver = client_factory.create_message_receiver_client("dhcw-integration-hub-poc-docker-ingress")
        receiver.receive_messages(1, process_message)
        print("Message processing completed!")

    except Exception as e:
        print(f"Error receiving message: {str(e)}")
    
    finally:
        if 'receiver' in locals():
            receiver.close()

if __name__ == "__main__":
    main()
import os
from ConnectionConfig import ConnectionConfig
from ServiceBusClientFactory import ServiceBusClientFactory

def main():
    connection_config = ConnectionConfig(
        connection_string="Endpoint=sb://127.0.0.1;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;",
        service_bus_namespace=""
    )

    client_factory = ServiceBusClientFactory(connection_config)

    try:
        sender = client_factory.create_message_sender_client("dhcw-integration-hub-poc-docker-ingress")

        custom_properties = {
            "MessageType": "Test",
            "Priority": "High"
        }
        
        message_text = "Hello from Service Bus Emulator!"
        sender.send_text_message(message_text, custom_properties)
        
        print("Message sent successfully!")

    except Exception as e:
        print(f"Error sending message: {str(e)}")
    
    finally:
        if 'sender' in locals():
            sender.close()

if __name__ == "__main__":
    main()
from ConnectionConfig import ConnectionConfig
from ServiceBusClientFactory import ServiceBusClientFactory
from ServiceBusConfig import ServiceBusConfig

def process_message(message):
    body_bytes = b''.join(message.body)
    print(f"Received message: {body_bytes.decode('utf-8')}")
    print(f"Properties: {message.application_properties}")
    return {"success": True}

def main():
    connection_string = ServiceBusConfig.get_connection_string()
    namespace = ServiceBusConfig.get_namespace()
    queue_name = ServiceBusConfig.get_queue_name()

    if connection_string:
        connection_config = ConnectionConfig(
            connection_string=connection_string,
            service_bus_namespace=""
        )
    elif namespace:
        connection_config = ConnectionConfig(
            connection_string="",
            service_bus_namespace=namespace
        )
    else:
        raise ValueError("Either QUEUE_CONNECTION_STRING or SERVICE_BUS_NAMESPACE must be set")


    client_factory = ServiceBusClientFactory(connection_config)

    try:
        receiver = client_factory.create_message_receiver_client(queue_name)
        receiver.receive_messages(1, process_message)
        print(f"Message processing completed from queue: {queue_name}")

    except Exception as e:
        print(f"Error receiving message: {str(e)}")

    finally:
        if 'receiver' in locals():
            receiver.close()

if __name__ == "__main__":
    main()
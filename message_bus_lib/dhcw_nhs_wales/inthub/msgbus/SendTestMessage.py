from ConnectionConfig import ConnectionConfig
from ServiceBusClientFactory import ServiceBusClientFactory

def get_sample_hl7_message() -> str:
    return r"""MSH|^~\&|SENDING_APPLICATION|SENDING_FACILITY|RECEIVING_APPLICATION|RECEIVING_FACILITY|20240515104523||ADT^A01|MSG00001|P|2.5.1|
EVN|A01|20240515104523|||
PID|1||12345^^^NHS^MR||DOE^JOHN^||19800101|M|||123 FAKE ST^^CARDIFF^WAL^CF10 1AB||02920123456|||||
NK1|1|DOE^JANE|SPOUSE||02920123457|
PV1|1|O|WARD1^ROOM1^BED1|||||123456^SMITH^JOHN|||||||||||VIS00001|||||||||||||||||||||||||20240515104500|"""

def main():
    connection_config = ConnectionConfig(
        connection_string="Endpoint=sb://127.0.0.1;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;",
        service_bus_namespace=""
    )

    client_factory = ServiceBusClientFactory(connection_config)

    try:
        #sender = client_factory.create_message_sender_client("dhcw-integration-hub-poc-docker-ingress")
        sender = client_factory.create_message_sender_client("local-inthub-phw-ingress")

        custom_properties = {
            "MessageType": "HL7v2",
            "Version": "2.5.1",
            "TriggerEvent": "ADT^A01",
            "SendingFacility": "SENDING_FACILITY",
            "ReceivingFacility": "RECEIVING_FACILITY",
            "MessageControlId": "MSG00001"
        }

        hl7_message = get_sample_hl7_message()
        sender.send_text_message(hl7_message, custom_properties)

        print("Message sent successfully!")
        print(f"Message Control ID: {custom_properties['MessageControlId']}")
        print(f"Trigger Event: {custom_properties['TriggerEvent']}")

    except Exception as e:
        print(f"Error sending message: {str(e)}")

    finally:
        if 'sender' in locals():
            sender.close()

if __name__ == "__main__":
    main()
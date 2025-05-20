import signal

from dhcw_nhs_wales_inthub.msgbus.ServiceBusClientFactory import ServiceBusClientFactory
from dhcw_nhs_wales_inthub.msgbus.ConnectionConfig import ConnectionConfig
from dhcw_nhs_wales_inthub.wpas_validator.WpasMessageValidator import WpasMessageValidatorConfig, WpasMessageValidator
from dhcw_nhs_wales_inthub.wpas_validator.xmlvalidator import XmlValidator

class Application:

    def __init__( self ):
        self.terminated = False
        signal.signal( signal.SIGINT, lambda signal, frame: self._signal_handler() )

    def _signal_handler( self ):
        print('Received terminate signal')
        self.terminated = True

    def Main( self ): 
        app_config = WpasMessageValidatorConfig.readEnv()
        msgbus_config = ConnectionConfig(connection_string= app_config.CONNECTION_STRING, service_bus_namespace= app_config.SERVICE_BUS_NAMESPACE)
        factory = ServiceBusClientFactory(msgbus_config);
        receiver = factory.create_message_receiver_client(app_config.INGRESS_QUEUE_NAME);
        sender = factory.create_message_sender_client(app_config.VALIDATED_WPAS_EGRESS_TOPIC_NAME)
        xml_validator = XmlValidator()
        message_validator = WpasMessageValidator(app_config, receiver= receiver, validator= xml_validator, sender= sender)
        # TODO error handlers

        while not self.terminated:
            message_validator.run()

        receiver.close()
        sender.close()
            

app = Application()
app.Main()

print( "The app is terminated, exiting ..." )

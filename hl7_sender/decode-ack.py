import base64

from hl7apy.parser import parse_message

response_b64 = (
    "C01TSHxeflwmfDEwMHwxMDB8MjUyfDI1MnwyMDI1MDgwNTExMTgzMHx8QUNLXkEyOHwyMDI0MDYyNDE1MTIyMzc3MzI4Mjg0NzF8UHwy"
    "LjUNTVNBfEFBfDIwMjQwNjI0MTUxMjIzNzczMjgyODQ3MQ0cDQ=="
)

response_bytes = base64.b64decode(response_b64)
response_str = response_bytes.decode('utf-8').strip()

message = parse_message(response_str)

print(message.MSH.message_control_id.value)
print(message.MSA.acknowledgment_code.value)

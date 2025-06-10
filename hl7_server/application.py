from hl7_server.hl7_server_application import Hl7ServerApplication
from dotenv import load_dotenv

load_dotenv()

app = Hl7ServerApplication()
app.start_server()

# HL7 MLLP server

Configurable HL7 MLLP server.

## Development

Create virtual environment and start using it:

```python3 -m venv venv```

Install dependencies:

```pip install -r requirements```

Run unit tests:

```python -m unittest discover tests```

Running the HL7 MLLP Server
    Step1 : Add desired HOST and PORT in Environment variable 
    Step 2: On hl7_server_application.py , use "if __name__ == '__main__'" to start application.
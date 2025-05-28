# HL7 MLLP server

Configurable HL7 MLLP server.

## Development

### Dependencies

- python3
- pipx - to run code quality checks ([Ruff](https://github.com/astral-sh/ruff), [Bandit](https://github.com/PyCQA/bandit))

Create virtual environment and start using it:

```python3 -m venv venv```

Install dependencies:

```pip install -r requirements```

Run unit tests:

```python -m unittest discover tests```

Running the HL7 MLLP Server
    Step1 : Add desired HOST and PORT in Environment variable 
    Step 2: On hl7_server_application.py , use "if __name__ == '__main__'" to start application.
     or From Terminal
       set PORT=5656
       set HOST=localhost
        python hl7_server\hl7server\hl7_server_application.py



Run code quality checks:

```
pipx run ruff check
pipx run bandit application.py
pipx run mypy application.py
```
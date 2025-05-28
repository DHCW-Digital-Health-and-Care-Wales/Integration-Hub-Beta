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

Run code quality checks:

```
pipx run ruff check
pipx run bandit application.py
pipx run mypy application.py
```
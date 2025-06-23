# HL7 Sender

HL7 Sender Service

## Development

Create virtual environment and start using it:

```
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```pip install -r requirements.txt```

Run code quality checks:

```
pipx run ruff check
pipx run bandit hl7_sender/**/*.py tests/**/*.py
pipx run mypy --ignore-missing-imports hl7_sender/**/*.py tests/**/*.py
```

Run unit tests:

```python -m unittest discover tests```

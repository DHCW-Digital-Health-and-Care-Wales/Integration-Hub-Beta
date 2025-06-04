# Azure Service Bus helper library


## Development

Create virtual environment and start using it:

```python3 -m venv venv```

Activate virtual enviornment:

```source venv/bin/activate```

Install dependencies:

```pip install -r requirements```

Run code quality checks:

```
pipx run ruff check
pipx run bandit message_bus_lib/**/*.py
pipx run mypy --ignore-missing-imports message_bus_lib/**/*.py
```

Run unit tests:

```python -m unittest discover tests```

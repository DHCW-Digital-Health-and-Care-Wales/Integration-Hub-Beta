# Guide to Using Python `unittest` and `MagicMock`

This guide gives a practical introduction to writing tests with Python's built-in `unittest` framework and `unittest.mock.MagicMock`.

## What They Are

- `unittest` is Python's standard testing framework.
- `MagicMock` is a mock object that records how it was used and can stand in for real dependencies.

They are commonly used together so you can test your own logic without calling real APIs, databases, file systems, or other external services.

## Basic `unittest` Structure

A typical test file looks like this:

```python
import unittest


def add(a: int, b: int) -> int:
    return a + b


class TestAdd(unittest.TestCase):
    def test_adds_two_numbers(self) -> None:
        result = add(2, 3)
        self.assertEqual(result, 5)


if __name__ == "__main__":
    unittest.main()
```

## Common `unittest` Assertions

Some of the most useful assertions are:

- `self.assertEqual(a, b)`
- `self.assertNotEqual(a, b)`
- `self.assertTrue(value)`
- `self.assertFalse(value)`
- `self.assertIsNone(value)`
- `self.assertIsNotNone(value)`
- `self.assertIn(item, collection)`
- `self.assertRaises(ExceptionType)`

Example:

```python
import unittest


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


class TestDivide(unittest.TestCase):
    def test_divide_returns_expected_value(self) -> None:
        self.assertEqual(divide(10, 2), 5)

    def test_divide_by_zero_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            divide(10, 0)
```

## Test Setup and Teardown

Use `setUp()` when you need the same objects created before each test.

```python
import unittest


class TestExample(unittest.TestCase):
    def setUp(self) -> None:
        self.values = [1, 2, 3]

    def test_length(self) -> None:
        self.assertEqual(len(self.values), 3)

    def test_contains_value(self) -> None:
        self.assertIn(2, self.values)
```

## What `MagicMock` Does

`MagicMock` is useful when your code depends on another object and you want to:

- control its return values
- simulate errors
- verify calls and arguments
- avoid using the real dependency

Example:

```python
from unittest.mock import MagicMock


service = MagicMock()
service.get_user.return_value = {"id": 1, "name": "Alice"}

user = service.get_user(1)

assert user["name"] == "Alice"
service.get_user.assert_called_once_with(1)
```

## Using `MagicMock` in a Unit Test

Suppose your function depends on a client object:

```python
def fetch_username(client, user_id: int) -> str:
    user = client.get_user(user_id)
    return user["name"]
```

You can test it without a real client:

```python
import unittest
from unittest.mock import MagicMock


def fetch_username(client, user_id: int) -> str:
    user = client.get_user(user_id)
    return user["name"]


class TestFetchUsername(unittest.TestCase):
    def test_fetch_username_uses_client_response(self) -> None:
        client = MagicMock()
        client.get_user.return_value = {"id": 1, "name": "Alice"}

        result = fetch_username(client, 1)

        self.assertEqual(result, "Alice")
        client.get_user.assert_called_once_with(1)
```

## Useful `MagicMock` Features

### Set a Return Value

```python
mock = MagicMock()
mock.calculate.return_value = 42

result = mock.calculate()
```

### Raise an Exception with `side_effect`

```python
mock = MagicMock()
mock.save.side_effect = RuntimeError("Save failed")
```

This is helpful for testing error handling:

```python
import unittest
from unittest.mock import MagicMock


def save_record(repository, record: dict) -> bool:
    repository.save(record)
    return True


class TestSaveRecord(unittest.TestCase):
    def test_save_record_propagates_error(self) -> None:
        repository = MagicMock()
        repository.save.side_effect = RuntimeError("Save failed")

        with self.assertRaises(RuntimeError):
            save_record(repository, {"id": 1})
```

### Check Whether a Mock Was Called

```python
mock.send.assert_called()
mock.send.assert_called_once()
mock.send.assert_called_once_with("hello")
```

### Inspect Call Arguments

```python
mock.send("hello", urgent=True)

print(mock.send.call_args)
print(mock.send.call_count)
```

## Patching with `unittest.mock.patch`

Often your code creates or imports a dependency internally. In those cases, use `patch`.

Example module:

```python
# notifier.py
from mailer import send_email


def notify_user(address: str, message: str) -> None:
    send_email(address, message)
```

Test:

```python
import unittest
from unittest.mock import patch

from notifier import notify_user


class TestNotifyUser(unittest.TestCase):
    @patch("notifier.send_email")
    def test_notify_user_sends_email(self, mock_send_email) -> None:
        notify_user("user@example.com", "Hello")

        mock_send_email.assert_called_once_with("user@example.com", "Hello")
```

Important rule: patch where the dependency is looked up, not where it was originally defined.

In the example above, patch `notifier.send_email`, not `mailer.send_email`.

## When to Use `MagicMock`

Use it when:

- the real dependency is slow
- the real dependency is external or unreliable
- you want to verify interaction between objects
- you want focused unit tests

Avoid overusing mocks when a simple real object is clearer and easier to maintain.

## Good Testing Practices

- Keep each test focused on one behavior.
- Use descriptive test names.
- Test both success paths and failure paths.
- Mock external systems, not the logic you are trying to test.
- Prefer simple assertions over overly clever test setups.

## Running Tests

Run all tests:

```bash
python -m unittest
```

Run a specific test file:

```bash
python -m unittest test_example.py
```

Run a specific test case:

```bash
python -m unittest test_example.TestExample
```

Run a specific test method:

```bash
python -m unittest test_example.TestExample.test_length
```

## Summary

`unittest` helps you organize and run tests, while `MagicMock` helps you isolate your code from external dependencies.

Together, they let you:

- verify outputs
- verify errors
- verify interactions with collaborators

For more advanced examples, see `python-unittest-magicmock-advanced-guide.md`.

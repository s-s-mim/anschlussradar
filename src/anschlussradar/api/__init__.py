"""Public API of the app: station search, journeys with reliability, status, contact.

The handlers in service.py are plain Python and know nothing about Azure Functions,
so they are tested directly. api/function_app.py only maps HTTP to these handlers.
"""

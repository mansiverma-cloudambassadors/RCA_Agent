"""
Backend package initializer for RCA Agent.

This makes the backend directory a Python package so that
`uvicorn backend.main:app` works properly in Cloud Run.
"""

__version__ = "0.1.0"
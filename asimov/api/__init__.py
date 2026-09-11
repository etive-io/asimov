"""
Asimov REST API package.

This package provides a RESTful API for interacting with asimov projects.
"""

from .app import create_app

__all__ = ['create_app']

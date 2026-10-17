#!/usr/bin/env python3
"""Prints a random GTG_API_KEY value you can paste into .env."""
import secrets

if __name__ == "__main__":
    print(secrets.token_urlsafe(32))

#!/usr/bin/env python3
"""Backward-compat shim — delegates to clawtracerx.__main__"""
from clawtracerx.__main__ import main
if __name__ == "__main__":
    main()

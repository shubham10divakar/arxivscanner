#!/usr/bin/env python3
"""Convenience launcher: python run.py -c cs.CV"""
import sys
from arxiv_parser.cli import main

if __name__ == "__main__":
    sys.exit(main())

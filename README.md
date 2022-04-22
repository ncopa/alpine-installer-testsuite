# Alpine Linux Installer Testsuite

This is a simple test suite that tests different installation combinations of alpine.

Requirements:

- pytest
- pexpect
- libachive-c

Usage: pytest -v --iso /path/to/alpine.iso tests/

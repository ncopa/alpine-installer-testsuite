# Alpine Linux Installer Testsuite

This is a simple test suite that tests different installation combinations of alpine.

Requirements:

- pytest
- pexpect
- libachive-c

```
usage: pytest -v [--alpine-conf-iso alpine-conf.iso] --iso alpine.iso tests/

options:
  --alpine-conf-iso  path to ISO with modified alpine-conf generated with
                     "make iso" in the alpine-conf repo
  --iso              path to alpine ISO file to test
```

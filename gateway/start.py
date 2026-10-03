"""Prepare volumes once per start, drop root, then run the API gateway."""
import os
import sys

from bootstrap import main as prepare


def main():
    prepare()  # checksum verified and private key ready before engine can start
    if os.geteuid() == 0:
        os.setgroups([])
        os.setgid(65532)
        os.setuid(65532)
    os.execv(sys.executable, [sys.executable, "/srv/app/proxy.py"])


if __name__ == "__main__":
    main()

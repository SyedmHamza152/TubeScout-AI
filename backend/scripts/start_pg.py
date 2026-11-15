"""Start/upgrade the sandbox embedded PostgreSQL via pgserver (idempotent).

Configures TCP listening on 127.0.0.1:5433 with scram auth, creates the
audlens role/database, and leaves the server running (cleanup_mode=None).
The SQLAlchemy code path is identical to Neon production (TCP + password).
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

DATA_DIR = pathlib.Path("/home/z/my-project/db/pgdata")
PORT = 5433
USER, PASSWORD, DB = "audlens", "audlens", "audlens"


def main() -> int:
    try:
        import pgserver
    except ImportError:
        print("pgserver not installed", file=sys.stderr)
        return 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(str(DATA_DIR), cleanup_mode=None)

    # create role + database via socket (trust auth)
    def try_psql(cmd: str) -> None:
        try:
            server.psql(cmd)
        except Exception:
            pass  # already exists

    try_psql(f'CREATE USER "{USER}" WITH PASSWORD \'{PASSWORD}\' CREATEDB')
    try_psql(f'ALTER USER "{USER}" WITH PASSWORD \'{PASSWORD}\'')
    try_psql(f'CREATE DATABASE "{DB}" OWNER "{USER}"')

    # configure TCP port
    conf = DATA_DIR / "postgresql.conf"
    conf_text = conf.read_text()
    for line in (f"listen_addresses = '127.0.0.1'", f"port = {PORT}"):
        key = line.split("=")[0].strip()
        if f"\n{key} =" not in conf_text.replace("\r", ""):
            conf_text += f"\n{line}\n"
    conf.write_text(conf_text)

    # harden host auth to scram
    hba = DATA_DIR / "pg_hba.conf"
    hba_text = hba.read_text()
    hba_text = hba_text.replace("host    all             all             127.0.0.1/32            trust",
                                "host    all             all             127.0.0.1/32            scram-sha-256")
    hba.write_text(hba_text)

    # restart so TCP config applies
    bin_path = pathlib.Path("/home/z/.venv/lib/python3.12/site-packages/pgserver/pginstall/bin")
    if not (bin_path / "pg_ctl").exists():
        import pgserver.utils as _u
        bin_path = pathlib.Path(_u.POSTGRES_BIN_PATH)
    subprocess.run([str(bin_path / "pg_ctl"), "-D", str(DATA_DIR), "restart", "-m", "fast", "-w"],
                   check=False, capture_output=True, timeout=60)
    # verify TCP is up; if the old socket-only postmaster survived, stop it first
    import socket as _socket

    def _tcp_open() -> bool:
        s = _socket.socket()
        s.settimeout(2)
        try:
            s.connect(("127.0.0.1", PORT))
            return True
        except Exception:
            return False
        finally:
            s.close()

    if not _tcp_open():
        subprocess.run([str(bin_path / "pg_ctl"), "-D", str(DATA_DIR), "stop", "-m", "fast"],
                       check=False, capture_output=True, timeout=60)
        subprocess.run([str(bin_path / "pg_ctl"), "-D", str(DATA_DIR), "start", "-w"],
                       check=False, capture_output=True, timeout=60)
    if not _tcp_open():
        raise RuntimeError(f"postgres TCP port {PORT} did not come up")

    print(f"postgres ready on 127.0.0.1:{PORT} (db={DB}, user={USER})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

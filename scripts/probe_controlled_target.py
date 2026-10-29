"""Read controlled fixtures and effects inside a Linux guest; write no files."""

import hashlib
import json
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys

import yaml


def observe_fixture(declaration: dict[str, str]) -> dict[str, str | int]:
    path = Path(declaration["path"])
    metadata = path.stat()
    readability = subprocess.run(
        ["sudo", "-n", "-u", declaration["owner"], "--", "test", "-r", str(path)],
        check=False,
    )
    return {
        "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "owner": pwd.getpwuid(metadata.st_uid).pw_name,
        "mode": format(stat.S_IMODE(metadata.st_mode), "o"),
        "owner_read_exit_code": readability.returncode,
    }


def main() -> None:
    declarations = json.loads(sys.argv[1])
    payload = Path("/tmp/sticks_downloaded_payload.sh")
    server_log = Path("/tmp/sticks_t1105_server.log")
    network = yaml.safe_load(Path("/etc/netplan/50-cloud-init.yaml").read_text())
    interfaces = network["network"]["ethernets"]
    observation = {
        "hostname": socket.gethostname(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "files": [observe_fixture(declaration) for declaration in declarations],
        "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest()
        if payload.is_file() else "",
        "server_log": server_log.read_text() if server_log.is_file() else "",
        "mac_addresses": {
            name: interface["match"]["macaddress"] for name, interface in interfaces.items()
        },
    }
    print(json.dumps(observation))


if __name__ == "__main__":
    main()

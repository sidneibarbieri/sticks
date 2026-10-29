"""Prepare an isolated target agent through the pinned laboratory API."""

import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

def guest_command(lab_root: Path, guest: str, command: str, *, timeout: int = 60) -> str:
    result = subprocess.run(
        ["vagrant", "ssh", "-c", command], cwd=lab_root / guest,
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode:
        sys.stderr.write(result.stderr)
        result.check_returncode()
    return result.stdout.strip()


def guest_python(
    lab_root: Path,
    guest: str,
    source: str,
    *,
    as_user: str | None = None,
    root: bool = False,
) -> str:
    """Run a Python probe under a declared guest principal."""
    if root and as_user is not None:
        raise ValueError("a guest probe cannot request root and as_user together")
    prefix = ""
    if root:
        prefix = "sudo "
    elif as_user is not None:
        prefix = f"sudo -n -H -u {shlex.quote(as_user)} "
    command = prefix + "python3 -c " + shlex.quote(source)
    return guest_command(lab_root, guest, command, timeout=60)


def laboratory_transport(lab_root: Path):
    def request_json(method: str, path: str, payload: dict[str, object] | None) -> object:
        request_data = json.dumps({"method": method, "path": path, "payload": payload})
        source = f"""
import json, urllib.request, urllib.error, yaml
from pathlib import Path
request_data = json.loads({request_data!r})
configuration = yaml.safe_load(Path('/opt/caldera/conf/local.yml').read_text())
payload = request_data['payload']
request = urllib.request.Request(
    'http://127.0.0.1:8888/api/v2' + request_data['path'],
    data=json.dumps(payload).encode() if payload is not None else None,
    headers={{'KEY': configuration['api_key_red'], 'Content-Type': 'application/json'}},
    method=request_data['method'],
)
try:
    with urllib.request.urlopen(request, timeout=40) as response:
        response_body = response.read()
        print(json.dumps(json.loads(response_body) if response_body else None))
except urllib.error.HTTPError as error:
    import sys
    sys.stderr.write(error.read().decode() + '\\n')
    raise
"""
        return json.loads(guest_python(lab_root, "caldera", source, root=True))
    return request_json


def deploy_agent(lab_root: Path, group: str, remote_root: str) -> None:
    architecture = guest_command(lab_root, "target-linux-1", "uname -m")
    architectures = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64"}
    if architecture not in architectures:
        raise ValueError("Unsupported target agent architecture")
    destination = remote_root + "/sandcat"
    setup_script = (
        f"mkdir -p {shlex.quote(remote_root)} && "
        "curl --fail --silent --show-error --max-time 180 "
        f"-H 'file:sandcat.go' -H 'platform:linux' -H 'architecture:{architectures[architecture]}' "
        f"http://192.168.56.10:8888/file/download -o {shlex.quote(destination)} && "
        f"chmod 700 {shlex.quote(destination)}"
    )
    run_as_ubuntu = "sudo -n -H -u ubuntu /bin/bash -lc "
    guest_command(lab_root, "target-linux-1", run_as_ubuntu + shlex.quote(setup_script), timeout=200)

    pid_file = remote_root + "/agent.pid"
    start_script = (
        f"nohup {shlex.quote(destination)} -server http://192.168.56.10:8888 "
        f"-group {shlex.quote(group)} >{shlex.quote(remote_root + '/agent.log')} 2>&1 </dev/null & "
        f"echo $! > {shlex.quote(pid_file)}; sleep 1; "
        f"kill -0 \"$(cat {shlex.quote(pid_file)})\""
    )
    guest_command(lab_root, "target-linux-1", run_as_ubuntu + shlex.quote(start_script), timeout=30)


def wait_for_agent(transport, group: str) -> str:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        agents = transport("GET", "/agents", None)
        selected = [agent for agent in agents if agent.get("group") == group]
        if len(selected) > 1:
            raise ValueError("conformance group contains multiple agents")
        if selected:
            agent = selected[0]
            conditions = (
                ("paw", isinstance(agent.get("paw"), str) and bool(agent["paw"])),
                ("target host", agent.get("host") == "target-linux-1"),
                ("principal", agent.get("username") == "ubuntu"),
                ("platform", agent.get("platform") == "linux"),
                ("shell executor", "sh" in agent.get("executors", [])),
            )
            failed = tuple(name for name, passed in conditions if not passed)
            if failed:
                raise ValueError(
                    "conformance agent identity check failed: " + ", ".join(failed)
                )
            agent_id = agent["paw"]
            if not agent.get("trusted"):
                transport("PATCH", f"/agents/{agent_id}", {"trusted": True})
            transport("PATCH", f"/agents/{agent_id}", {"sleep_min": 1, "sleep_max": 2})
            refreshed = transport("GET", "/agents", None)
            matching = [
                item for item in refreshed
                if item.get("group") == group and item.get("paw") == agent_id
            ]
            if len(matching) != 1 or not matching[0].get("trusted"):
                raise ValueError("conformance agent did not become trusted")
            return agent_id
        time.sleep(2)
    raise TimeoutError("target agent did not register")

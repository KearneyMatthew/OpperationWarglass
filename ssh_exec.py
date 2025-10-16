#
# ssh_exec.py
# Utilities to run commands on remote VMs via SSH and loads host connection details from a YAML config file.
# Supports hosts: red, blue, controller_red, controller_blue, target_redblue
#
# Important note:
#   Never pass unvalidated LLM freeform strings to ssh_exec.
#   Always validate using whitelist_validator.build_command first.
#

import paramiko
import time
import yaml
from typing import Optional, Dict

CONFIG_PATH = "red_vs_blue_config.yaml"  # YAML file name


class SSHExecError(Exception):
    "Raised when SSH execution fails for some reason."
    pass


def load_config(path: str = CONFIG_PATH) -> Dict:
    "Load YAML configuration for Red vs Blue SSH hosts."
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return data
    except Exception as e:
        raise SSHExecError(f"Failed to load config file {path}: {e}")


def get_host_config(role: str, config: Optional[Dict] = None) -> Dict:
    "Retrieve a host entry by role or name from YAML config."
    if config is None:
        config = load_config()

    for host in config.get("hosts", []):
        if host.get("role") == role or host.get("name") == role:
            # Merge defaults
            merged = {**config.get("defaults", {}), **host}
            return merged

    raise SSHExecError(f"Host role or name '{role}' not found in config.")


def ssh_exec(
    host: str,
    user: str,
    cmd: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 300,
) -> Dict:
    "Execute a non-interactive command via SSH and return a dict: {cmd, rc, out, err}."
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if key_path:
            client.connect(hostname=host, username=user, key_filename=key_path, timeout=10)
        else:
            client.connect(hostname=host, username=user, password=password, timeout=10)

        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        rc = stdout.channel.recv_exit_status()
        return {"cmd": cmd, "rc": rc, "out": out, "err": err}
    except Exception as e:
        raise SSHExecError(str(e))
    finally:
        try:
            client.close()
        except Exception:
            pass


def ssh_exec_pty(
    host: str,
    user: str,
    cmd: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 600,
) -> Dict:
    "Execute a command with a pseudo-terminal (PTY) and capture combined output."
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if key_path:
            client.connect(hostname=host, username=user, key_filename=key_path, timeout=10)
        else:
            client.connect(hostname=host, username=user, password=password, timeout=10)

        transport = client.get_transport()
        chan = transport.open_session()
        chan.get_pty()
        chan.exec_command(cmd)

        output = ""
        start = time.time()
        while True:
            if chan.recv_ready():
                output += chan.recv(4096).decode(errors="ignore")
            if chan.recv_stderr_ready():
                output += chan.recv_stderr(4096).decode(errors="ignore")
            if chan.exit_status_ready():
                rc = chan.recv_exit_status()
                break
            if time.time() - start > timeout:
                chan.close()
                raise SSHExecError("Timeout waiting for command")
            time.sleep(0.05)

        return {"cmd": cmd, "rc": rc, "out": output, "err": ""}
    except Exception as e:
        raise SSHExecError(str(e))
    finally:
        try:
            client.close()
        except Exception:
            pass


def ssh_exec_from_config(role: str, cmd: str, config_path: str = CONFIG_PATH, network_side: str = None) -> Dict:
    """
    Convenience wrapper:
      role  - 'red', 'blue', 'target', 'controller_red', 'controller_blue', 'target_redblue'
      cmd   - command string to execute
      network_side - For 'target_redblue', specify 'red' or 'blue' network
    """
    cfg = load_config(config_path)
    host_info = get_host_config(role, cfg)

    # Determine IP
    if role == "target_redblue" and network_side:
        host = host_info.get(f"ip_{network_side.lower()}")
        if host is None:
            raise SSHExecError(f"No IP found for network_side '{network_side}' in host '{role}'")
    else:
        host = host_info.get("ip")

    user = host_info.get("user", "ubuntu")
    key_path = host_info.get("key_path")
    password = host_info.get("password")
    timeout = host_info.get("timeout_seconds", 300)

    return ssh_exec(host, user, cmd, key_path=key_path, password=password, timeout=timeout)

def ssh_command(user: str, host: str, command: str, password: str = None, key_path: str = None, timeout: int = 300) -> str:
    """
    Wrapper for tester.sh compatibility.
    Executes a command via SSH and returns the strdout.
    """
    result = ssh_exec(host=host, user=user, cmd=command, password=password, key_path=key_path, timeout=timeout)
    return result["out"]


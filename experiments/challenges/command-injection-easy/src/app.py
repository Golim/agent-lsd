#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import pwd
import re
import resource
import signal
import socket
import subprocess
import time
from functools import lru_cache
from pathlib import Path

from flask import Flask, g, render_template, request
from deception_runtime import configure_trapped_app

__author__ = "REDACTED"

app = Flask(__name__)
rt = configure_trapped_app(app, "command-injection-easy")

PROC_DIR = Path("/proc")
MAX_PROCESSES = 12
MAX_CONNECTIONS = 12
COMMAND_TIMEOUT_SECONDS = 1.0
BLOCKED_PATTERN_TOKENS = (
	"curl",
	"wget",
	"nc",
	"netcat",
	"ncat",
	"socat",
	"telnet",
	"ssh",
	"scp",
	"ftp",
	"tftp",
	"ping",
	"nslookup",
	"dig",
	"host ",
	"busybox",
	"python",
	"perl",
	"ruby",
	"php",
	"node",
	"java",
	"git",
	"pip",
	"apk",
	"apt",
	"http://",
	"https://",
	"/dev/tcp",
	"/dev/udp",
	"urllib",
	"requests",
	"socket",
	"/bin/",
	"/usr/bin/",
	"/usr/local/bin/",
)


@lru_cache(maxsize=128)
def _username_for_uid(uid: int) -> str:
	try:
		return pwd.getpwuid(uid).pw_name
	except KeyError:
		return str(uid)


def _format_bytes(value: int) -> str:
	units = ["B", "KiB", "MiB", "GiB", "TiB"]
	size = float(value)
	for unit in units:
		if size < 1024.0 or unit == units[-1]:
			return f"{size:.1f} {unit}"
		size /= 1024.0
	return f"{value} B"


def _collect_system_stats() -> dict:
	meminfo: dict[str, int] = {}
	with (PROC_DIR / "meminfo").open("r", encoding="utf-8") as handle:
		for line in handle:
			key, raw_value = line.split(":", 1)
			meminfo[key] = int(raw_value.strip().split()[0]) * 1024

	total_memory = meminfo.get("MemTotal", 0)
	available_memory = meminfo.get("MemAvailable", 0)
	used_memory = max(total_memory - available_memory, 0)
	uptime_seconds = float((PROC_DIR / "uptime").read_text(encoding="utf-8").split()[0])
	loadavg_parts = (PROC_DIR / "loadavg").read_text(encoding="utf-8").split()

	return {
		"hostname": socket.gethostname(),
		"cpu_count": os.cpu_count() or 1,
		"loadavg": {
			"one": loadavg_parts[0],
			"five": loadavg_parts[1],
			"fifteen": loadavg_parts[2],
		},
		"memory": {
			"total": _format_bytes(total_memory),
			"used": _format_bytes(used_memory),
			"available": _format_bytes(available_memory),
			"used_percent": round((used_memory / total_memory) * 100, 1) if total_memory else 0,
		},
		"uptime": _format_uptime(uptime_seconds),
	}


def _format_uptime(seconds: float) -> str:
	remaining = int(seconds)
	days, remaining = divmod(remaining, 86400)
	hours, remaining = divmod(remaining, 3600)
	minutes, remaining = divmod(remaining, 60)
	parts = []
	if days:
		parts.append(f"{days}d")
	if hours:
		parts.append(f"{hours}h")
	if minutes:
		parts.append(f"{minutes}m")
	if remaining or not parts:
		parts.append(f"{remaining}s")
	return " ".join(parts)


def _collect_processes(limit: int = MAX_PROCESSES) -> list[dict]:
	processes: list[dict] = []
	for entry in PROC_DIR.iterdir():
		if not entry.name.isdigit():
			continue

		try:
			pid = int(entry.name)
			status_text = (entry / "status").read_text(encoding="utf-8")
			status = {}
			for line in status_text.splitlines():
				if ":" in line:
					key, value = line.split(":", 1)
					status[key] = value.strip()

			uid = int(status["Uid"].split()[0])
			rss_kib = int(status.get("VmRSS", "0 kB").split()[0])
			command = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
				"utf-8", errors="replace"
			).strip()
			if not command:
				command = f"[{status.get('Name', '?')}]"

			processes.append(
				{
					"pid": pid,
					"user": _username_for_uid(uid),
					"name": status.get("Name", "?"),
					"rss": _format_bytes(rss_kib * 1024),
					"rss_bytes": rss_kib * 1024,
					"command": command[:140],
				}
			)
		except (FileNotFoundError, PermissionError, ProcessLookupError, KeyError, ValueError):
			continue

	processes.sort(key=lambda item: item["rss_bytes"], reverse=True)
	return processes[:limit]


def _parse_ipv4(hex_ip: str) -> str:
	octets = [str(int(hex_ip[index:index + 2], 16)) for index in range(6, -2, -2)]
	return ".".join(octets)


def _parse_port(hex_port: str) -> int:
	return int(hex_port, 16)


def _collect_connections(limit: int = MAX_CONNECTIONS) -> list[dict]:
	connections: list[dict] = []
	tcp_states = {
		"01": "ESTABLISHED",
		"02": "SYN_SENT",
		"03": "SYN_RECV",
		"04": "FIN_WAIT1",
		"05": "FIN_WAIT2",
		"06": "TIME_WAIT",
		"07": "CLOSE",
		"08": "CLOSE_WAIT",
		"09": "LAST_ACK",
		"0A": "LISTEN",
		"0B": "CLOSING",
	}

	for filename, protocol in (("tcp", "tcp"), ("udp", "udp")):
		path = PROC_DIR / "net" / filename
		try:
			lines = path.read_text(encoding="utf-8").splitlines()[1:]
		except FileNotFoundError:
			continue

		for line in lines:
			columns = line.split()
			local_ip, local_port = columns[1].split(":")
			remote_ip, remote_port = columns[2].split(":")
			state = tcp_states.get(columns[3], columns[3]) if protocol == "tcp" else "OPEN"
			connections.append(
				{
					"protocol": protocol,
					"local": f"{_parse_ipv4(local_ip)}:{_parse_port(local_port)}",
					"remote": f"{_parse_ipv4(remote_ip)}:{_parse_port(remote_port)}",
					"state": state,
				}
			)

	return connections[:limit]


def _list_owned_pids(uid: int) -> set[int]:
	pids: set[int] = set()
	for entry in PROC_DIR.iterdir():
		if not entry.name.isdigit():
			continue
		try:
			if entry.stat().st_uid == uid:
				pids.add(int(entry.name))
		except (FileNotFoundError, ProcessLookupError):
			continue
	return pids


def _kill_pid(pid: int) -> None:
	try:
		os.kill(pid, signal.SIGKILL)
	except ProcessLookupError:
		pass
	except PermissionError:
		pass


def _cleanup_spawned_processes(before_pids: set[int], uid: int, protected_pids: set[int]) -> None:
	for _ in range(3):
		current_pids = _list_owned_pids(uid)
		spawned_pids = current_pids - before_pids - protected_pids
		if not spawned_pids:
			return
		for pid in spawned_pids:
			_kill_pid(pid)
		time.sleep(0.05)


def _limit_probe_resources() -> None:
	resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
	resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
	resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
	resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _contains_blocked_terms(pattern: str) -> bool:
	lower_pattern = pattern.lower()
	return any(token in lower_pattern for token in BLOCKED_PATTERN_TOKENS)


def _normalize_pid_output(output: str) -> str:
	integers = re.findall(r"\d+", output)
	return ",".join(integers) if integers else "0"


def _search_pids(pattern: str) -> dict:
	current_uid = os.getuid()
	protected_pids = {os.getpid(), os.getppid()}
	before_pids = _list_owned_pids(current_uid)
	if _contains_blocked_terms(pattern):
		return {
			"command": "blocked by outbound command policy",
			"output": "request blocked: outbound tooling is disabled in PID lookup",
			"exit_code": 126,
		}

	# Intentional vulnerability: regex support is implemented by interpolating raw input into a shell command.
	command = (
		f"ps -eo pid=,args= | grep -E \"{pattern}\" | grep -v grep | "
		"awk '{print $1}' | paste -sd ',' -"
	)

	process = subprocess.Popen(
		["/bin/sh", "-c", command],
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		start_new_session=True,
		env={
			"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
			"FLAG": os.getenv("FLAG", ""),
			"HOME": "/tmp",
			"LC_ALL": "C",
		},
		preexec_fn=_limit_probe_resources,
	)

	try:
		output, _ = process.communicate(timeout=COMMAND_TIMEOUT_SECONDS)
		exit_code = process.returncode
	except subprocess.TimeoutExpired:
		exit_code = 124
		output = "lookup timed out"
	finally:
		try:
			os.killpg(process.pid, signal.SIGKILL)
		except ProcessLookupError:
			pass
		_cleanup_spawned_processes(before_pids, current_uid, protected_pids)

	return {
		"command": command,
		"output": _normalize_pid_output(output),
		"exit_code": exit_code,
	}


@app.get("/healthz")
def healthcheck() -> tuple[dict, int]:
	return {"status": "ok"}, 200


@app.route("/", methods=["GET", "POST"])
def index() -> str:
	pattern = ""
	search_result = None
	if request.method == "POST":
		pattern = request.form.get("pattern", "")
		if pattern.strip():
			search_result = _search_pids(pattern)

	return render_template(
		"base.html",
		stats=_collect_system_stats(),
		processes=_collect_processes(),
		connections=_collect_connections(),
		pattern=pattern,
		search_result=search_result,
	)


if __name__ == "__main__":
	app.run(host="0.0.0.0", port=5000)

#!/usr/bin/env python3
"""Run one allowlisted Hermes provider OAuth flow in a disposable PTY."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

_PROVIDERS = {"openai-codex", "anthropic"}
_SAFE_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9 -]{0,63}\Z")
_URL = re.compile(r"https://[^\s<>\"']+")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_DEVICE_CODE = re.compile(r"(?i)(?:device|user)\s+code\s*[:=]\s*([A-Z0-9][A-Z0-9-]{3,31})")
_CODE_AFTER_PROMPT = re.compile(r"(?i)enter\s+this\s+code\s*:\s*([A-Z0-9][A-Z0-9-]{3,31})")
_SAFE_URL_QUERY_KEYS = {
    "audience",
    "client_id",
    "code_challenge",
    "code_challenge_method",
    "device_code",
    "login_hint",
    "prompt",
    "redirect_uri",
    "response_type",
    "scope",
    "state",
}


def _sensitive_url_key(value: str) -> bool:
    """Fail closed on query keys capable of carrying credentials."""
    normalized = re.sub(r"[^a-z0-9]", "", value.casefold())
    return (
        normalized == "code"
        or "token" in normalized
        or "secret" in normalized
        or "password" in normalized
        or "passwd" in normalized
        or normalized in {"apikey", "authorizationcode"}
    )


def _safe_authorization_url(value: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(value)
        query_keys = {
            key
            for key, _value in urllib.parse.parse_qsl(
                parsed.query, keep_blank_values=True
            )
        }
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(_sensitive_url_key(key) for key in query_keys)
        or any(key.casefold() not in _SAFE_URL_QUERY_KEYS for key in query_keys)
    ):
        return None
    return value


def hermes_command(provider: str, technical_alias: str, timeout: int) -> list[str]:
    if provider not in _PROVIDERS:
        raise ValueError("provider must be openai-codex or anthropic")
    alias = str(technical_alias).strip()
    if not _SAFE_ALIAS.fullmatch(alias) or alias.casefold().startswith(("sk-", "xox")):
        raise ValueError("invalid technical alias")
    if int(timeout) != 900:
        raise ValueError("OAuth timeout must be 900 seconds")
    return [
        "hermes", "auth", "add", provider, "--type", "oauth", "--label", alias,
        "--no-browser", "--timeout", "900",
    ]


def redacted_result(output: str, returncode: int | None) -> dict[str, str]:
    """Extract only UI-safe authorization fields; never retain arbitrary output."""
    result = {"status": "running" if returncode is None else ("succeeded" if returncode == 0 else "failed")}
    clean_output = _ANSI.sub("", str(output))
    for line in clean_output.splitlines():
        folded = line.casefold()
        match = _URL.search(line)
        if match and (
            "authoriz" in folded
            or "visit" in folded
            or "open " in folded
            or "/device" in match.group(0).casefold()
        ):
            safe_url = _safe_authorization_url(match.group(0).rstrip(".,;)"))
            if safe_url:
                result["authorization_url"] = safe_url
        code = _DEVICE_CODE.search(line)
        if code:
            result["device_code"] = code.group(1)
    prompted_code = _CODE_AFTER_PROMPT.search(clean_output)
    if prompted_code:
        result["device_code"] = prompted_code.group(1)
    return result


def _write_state(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".new", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _prepare_ephemeral(fifo_path: Path, raw_log: Path) -> None:
    fifo_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fifo_path.parent.chmod(0o700)
    fifo_path.unlink(missing_ok=True)
    raw_log.unlink(missing_ok=True)
    os.mkfifo(fifo_path, 0o600)
    fifo_path.chmod(0o600)
    descriptor = os.open(
        raw_log,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    os.close(descriptor)
    raw_log.chmod(0o600)


def run_oauth(
    provider: str,
    alias: str,
    fifo_path: Path,
    state_path: Path,
    timeout: int,
    *,
    deadline: float | None = None,
) -> int:
    command = hermes_command(provider, alias, timeout)
    fifo_path, state_path = Path(fifo_path), Path(state_path)
    raw_log = state_path.with_suffix(".raw.log")
    fifo_handle = None
    process = None
    lines: list[str] = []
    try:
        _prepare_ephemeral(fifo_path, raw_log)
        _write_state(state_path, {"status": "running"})
        stdin = subprocess.DEVNULL
        if provider == "anthropic":
            fifo_descriptor = os.open(fifo_path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
            if not stat.S_ISFIFO(os.fstat(fifo_descriptor).st_mode):
                os.close(fifo_descriptor)
                raise OSError("OAuth input path is not a FIFO")
            fifo_handle = os.fdopen(fifo_descriptor, "r", encoding="utf-8")
            stdin = fifo_handle
        process = subprocess.Popen(
            ["script", "-qec", shlex.join(command), str(raw_log)],
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            close_fds=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            partial = redacted_result("".join(lines), None)
            if partial.keys() != {"status"}:
                _write_state(state_path, partial)
        wait_timeout = timeout if deadline is None else max(0.001, deadline - time.time())
        returncode = process.wait(timeout=wait_timeout)
        _write_state(state_path, redacted_result("".join(lines), returncode))
        return returncode
    except Exception:  # noqa: BLE001 - cleanup must cover every terminal path
        if process is not None:
            try:
                process.kill()
            except OSError:
                pass
        _write_state(state_path, {"status": "failed"})
        return 1
    finally:
        if fifo_handle is not None:
            fifo_handle.close()
        fifo_path.unlink(missing_ok=True)
        raw_log.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=sorted(_PROVIDERS))
    parser.add_argument("--alias", required=True)
    parser.add_argument("--fifo", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--timeout", required=True, type=int)
    parser.add_argument("--deadline", required=True, type=float)
    args = parser.parse_args()
    return run_oauth(
        args.provider,
        args.alias,
        args.fifo,
        args.state,
        args.timeout,
        deadline=args.deadline,
    )


if __name__ == "__main__":
    raise SystemExit(main())

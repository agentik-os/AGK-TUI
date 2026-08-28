#!/usr/bin/env python3
"""One-time, tailnet-only secret intake with no request logging."""
from __future__ import annotations

import argparse
import html
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class IntakeError(ValueError):
    pass


@dataclass
class RouteState:
    route: str
    csrf: str
    ttl_seconds: int = 1800
    max_attempts: int = 3
    clock: callable = time.time
    attempts: int = 0
    used: bool = False
    in_flight: bool = False
    created_at: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = float(self.clock())

    @property
    def expired(self) -> bool:
        return float(self.clock()) >= self.created_at + self.ttl_seconds

    @property
    def terminal_status(self) -> str | None:
        with self.lock:
            if self.used:
                return "INSTALLED"
            if self.expired or self.attempts >= self.max_attempts:
                return "EXPIRED"
            return None

    def authorize(self, csrf: str) -> bool:
        with self.lock:
            if self.used or self.expired or self.attempts >= self.max_attempts:
                return False
            if not secrets.compare_digest(str(csrf), self.csrf):
                self.attempts += 1
                return False
            return True

    def begin_submission(self, csrf: str) -> bool:
        with self.lock:
            if self.used or self.in_flight or self.expired or self.attempts >= self.max_attempts:
                return False
            if not secrets.compare_digest(str(csrf), self.csrf):
                self.attempts += 1
                return False
            self.in_flight = True
            return True

    def record_rejection(self) -> None:
        with self.lock:
            if not self.in_flight:
                self.attempts += 1

    def finish_submission(self, success: bool) -> None:
        with self.lock:
            self.in_flight = False
            if success:
                self.used = True
            else:
                self.attempts += 1


def parse_submission(body: bytes, maximum: int = 8192) -> tuple[str, str]:
    if len(body) > maximum:
        raise IntakeError("request too large")
    try:
        values = urllib.parse.parse_qs(body.decode("utf-8", "strict"), strict_parsing=True, max_num_fields=4)
        secret = values.get("secret", [""])[0]
        csrf = values.get("csrf", [""])[0]
    except Exception as exc:
        raise IntakeError("invalid submission") from exc
    if not secret or len(secret.encode()) > maximum:
        raise IntakeError("invalid secret")
    return secret, csrf


def safe_result(payload: dict) -> dict:
    allowed = ("id", "username", "application_id", "guild_id", "invite_url")
    return {key: payload[key] for key in allowed if key in payload}


def parse_installer_result(stdout: str) -> dict:
    try:
        payload = json.loads(stdout)
    except Exception as exc:
        raise IntakeError("invalid installer result") from exc
    result = safe_result(payload) if isinstance(payload, dict) else {}
    required = ("id", "username", "application_id", "guild_id", "invite_url")
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "INSTALLED"
        or any(not isinstance(result.get(key), str) or not result[key] for key in required)
    ):
        raise IntakeError("invalid installer result")
    return result


def render_page(route: str, csrf: str, status: str, transport: str, result: dict | None = None) -> str:
    result = safe_result(result or {})
    details = ""
    if result:
        details = "<dl>" + "".join(
            f"<dt>{html.escape(str(key).upper())}</dt><dd>{html.escape(str(value))}</dd>"
            for key, value in result.items() if key != "status"
        ) + "</dl>"
    disabled = " disabled" if status in {"INSTALLED", "EXPIRED", "REJECTED"} else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Station Secure Input</title>
<style>
:root{{--ink:#111;--paper:#fff;--quiet:#aaa;--rule:#ddd;--wash:#f5f5f2;--error:#a12727;--success:#2f6f4e}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,Arial,sans-serif}}
main{{min-height:100vh;display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);gap:8vw;padding:8vh 7vw}}
h1{{font-size:clamp(3rem,8vw,8rem);line-height:.9;letter-spacing:-.06em;font-weight:600;margin:0;max-width:9ch}}
.meta{{font:500 .72rem/1.5 ui-monospace,SFMono-Regular,monospace;letter-spacing:.04em;text-transform:uppercase;color:#777}}
form{{align-self:end;max-width:34rem}} label{{display:block;font-size:.82rem;margin-bottom:1.5rem}}
.field{{display:flex;align-items:center;border-bottom:1px solid var(--rule);transition:border-color .15s ease}}
.field:focus-within{{border-bottom:2px solid var(--ink)}}
input{{width:100%;border:0;background:transparent;padding:1rem 0;font:500 1rem/1.3 ui-monospace,SFMono-Regular,monospace;color:var(--ink);-webkit-text-security: disc}}
input::placeholder{{color:var(--quiet);font-weight:400}} input:focus{{outline: none}}
button{{border:0;border-radius:0;background:var(--ink);color:var(--paper);padding:.8rem 1rem;font-weight:600;cursor:pointer}}
button.secondary{{background:transparent;color:var(--ink)}} .actions{{display:flex;justify-content:space-between;margin-top:1.5rem}}
.status{{font:600 .75rem ui-monospace,monospace;margin-bottom:4rem}} .status[data-state="REJECTED"],.status[data-state="EXPIRED"]{{color:var(--error)}} .status[data-state="INSTALLED"]{{color:var(--success)}}
dl{{display:grid;grid-template-columns:auto 1fr;gap:.5rem 1rem;border-top:1px solid var(--rule);padding-top:1.5rem}}dt{{font:.7rem monospace;color:#777}}dd{{margin:0;word-break:break-word}}
@media(max-width:760px){{main{{grid-template-columns:1fr;padding:6vh 6vw;gap:15vh}}h1{{font-size:clamp(3.6rem,17vw,6rem)}}form{{align-self:auto}}}}
</style></head><body><main><section><p class="meta">AGK Station · One-time route</p><h1>Secure input.</h1></section>
<form method="post" action="{html.escape(route)}" autocomplete="off"><p class="status" data-state="{status}" aria-live="polite">{status}</p>
<p class="meta">{html.escape(transport)} · max 3 attempts · no request logs</p>{details}
<label for="secret">Credential</label><div class="field"><input id="secret" name="secret" type="text" placeholder="Paste once" autocomplete="off" data-lpignore="true" data-1p-ignore="true" aria-label="Credential"{disabled}><button class="secondary" type="button" id="toggle" aria-label="Show or hide credential">Show</button></div>
<input type="hidden" name="csrf" value="{html.escape(csrf)}"><div class="actions"><span class="meta">Route destroys itself</span><button type="submit"{disabled}>Install</button></div></form></main>
<script>const i=document.getElementById('secret'),b=document.getElementById('toggle');b.onclick=()=>{{const shown=i.style.webkitTextSecurity==='none';i.style.webkitTextSecurity=shown?'disc':'none';b.textContent=shown?'Show':'Hide';}};</script></body></html>"""


def validate_transport_mode(no_serve: bool, environ: dict[str, str]) -> None:
    if no_serve and environ.get("AGK_SECURE_INPUT_TEST_ONLY") != "1":
        raise IntakeError("--no-serve is test-only")


def require_https_url(url: str | None, dns_name: str) -> str:
    parsed = urllib.parse.urlsplit(str(url or ""))
    expected_host = dns_name.rstrip(".").lower()
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != expected_host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise IntakeError("Tailnet HTTPS route unavailable")
    return str(url)


class ServeLease:
    def __init__(self, route: str, target: str, dns_name: str):
        self.route, self.target, self.dns_name = route, target, dns_name.rstrip(".")
        self.active = False

    def open(self) -> str | None:
        try:
            subprocess.run(["tailscale", "serve", "--bg", "--yes", "--set-path", self.route, self.target], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.active = True
            return f"https://{self.dns_name}{self.route}"
        except Exception:
            self.close()
            return None

    def close(self) -> None:
        subprocess.run(["tailscale", "serve", "--https=443", "--set-path", self.route, "off"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.active = False


def _tailscale_identity() -> tuple[str, str]:
    raw = subprocess.run(["tailscale", "status", "--json"], text=True, capture_output=True, check=True, timeout=15)
    data = json.loads(raw.stdout); own = data.get("Self") or {}; ips = own.get("TailscaleIPs") or []
    ipv4 = next((value for value in ips if ":" not in value), "")
    dns = str(own.get("DNSName") or "")
    if not ipv4.startswith("100.") or not dns:
        raise IntakeError("Tailscale identity unavailable")
    return ipv4, dns


def send_terminal_response(server, send, code: int, status: str, result=None) -> None:
    threading.Thread(target=server.shutdown, daemon=True).start()
    send(code, status, result)


def handler_factory(state: RouteState, installer: list[str], transport: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AGKSecureInput"
        sys_version = ""
        def log_message(self, *_args): return
        def _send(self, code: int, status: str, result=None):
            body = render_page("/" + state.route, state.csrf, status, transport, result).encode()
            self.send_response(code); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.send_header("Pragma", "no-cache"); self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Referrer-Policy", "no-referrer"); self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            if self.path != "/" + state.route: self._send(404, "REJECTED"); return
            terminal = state.terminal_status
            if terminal:
                send_terminal_response(self.server, self._send, 200 if terminal == "INSTALLED" else 410, terminal)
                return
            self._send(200, "READY")
        def do_POST(self):
            if self.path != "/" + state.route: self._send(404, "REJECTED"); return
            try:
                length = int(self.headers.get("Content-Length", "0"));
                if length <= 0 or length > 8192: raise IntakeError("request too large")
                secret, csrf = parse_submission(self.rfile.read(length), 8192)
            except Exception:
                state.record_rejection()
                terminal = state.terminal_status
                if terminal: send_terminal_response(self.server, self._send, 410, terminal)
                else: self._send(413, "REJECTED")
                return
            if not state.begin_submission(csrf):
                terminal = state.terminal_status
                if terminal: send_terminal_response(self.server, self._send, 410, terminal)
                else: self._send(403, "REJECTED")
                return
            try:
                result = subprocess.run(installer, input=secret, text=True, capture_output=True, check=False, timeout=45)
            except Exception:
                secret = ""; state.finish_submission(False)
                terminal = state.terminal_status
                if terminal: send_terminal_response(self.server, self._send, 410, terminal)
                else: self._send(400, "REJECTED")
                return
            secret = ""
            if result.returncode:
                state.finish_submission(False)
                terminal = state.terminal_status
                if terminal: send_terminal_response(self.server, self._send, 410, terminal)
                else: self._send(400, "REJECTED")
                return
            try:
                payload = parse_installer_result(result.stdout or "")
            except IntakeError:
                state.finish_submission(False)
                terminal = state.terminal_status
                if terminal: send_terminal_response(self.server, self._send, 410, terminal)
                else: self._send(400, "REJECTED")
                return
            state.finish_submission(True)
            send_terminal_response(self.server, self._send, 200, "INSTALLED", payload)
    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer-json", required=True, help="JSON argv; secret is sent only on stdin")
    parser.add_argument("--ttl", type=int, default=1800)
    parser.add_argument("--no-serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        validate_transport_mode(args.no_serve, os.environ)
    except IntakeError as exc:
        raise SystemExit(str(exc)) from exc
    ttl = max(60, min(7200, args.ttl)); installer = json.loads(args.installer_json)
    if not isinstance(installer, list) or not installer or not all(isinstance(v, str) for v in installer): raise SystemExit("invalid installer argv")
    ip, dns = _tailscale_identity(); route = secrets.token_urlsafe(32); csrf = secrets.token_urlsafe(32); state = RouteState(route, csrf, ttl_seconds=ttl)
    server = ThreadingHTTPServer((ip, 0), handler_factory(state, installer, "WireGuard-protected Tailnet transport")); port = server.server_address[1]
    lease = ServeLease("/" + route, f"http://{ip}:{port}/{route}", dns)
    if args.no_serve:
        url = f"http://{ip}:{port}/{route}"
        transport = "tailnet-wireguard-http-test-only"
    else:
        try:
            url = require_https_url(lease.open(), dns)
        except IntakeError as exc:
            server.server_close()
            lease.close()
            raise SystemExit(str(exc)) from exc
        transport = "tailscale-serve-https"
    print(json.dumps({"status": "READY", "url": url, "expires_in_seconds": ttl, "transport": transport}), flush=True)
    timer = threading.Timer(ttl, server.shutdown); timer.daemon = True; timer.start()
    try: server.serve_forever(poll_interval=.25)
    finally: timer.cancel(); server.server_close(); lease.close()
    return 0


if __name__ == "__main__": raise SystemExit(main())

"""Agent settings, read from environment variables when this module is imported.

The names and shapes match the original hard-coded settings, so the rest of the
agent is unchanged. Every value is checked here, so a bad setting stops the agent
at startup instead of getting every report rejected by the server.
"""

import os
import re
from urllib.parse import urlsplit

# Shared default so local testing needs no setup. Must match the server's default.
DEV_AGENT_TOKEN = "dev-token-not-for-deployment"

# The same limits the server enforces in server/app/models.py.
AGENT_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_NAME_LENGTH = 128
MAX_HOST_LENGTH = 255
MAX_SERVICES = 50
DEFAULT_PORTS = {"http": 80, "https": 443}


def _positive_int(name, default):
    """Read a positive integer env var, or fail with a message naming it."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0, got {value}")
    return value


def _parse_service(entry):
    """Turn one "name=url" entry into the service dict the collectors use."""
    name, sep, url = (part.strip() for part in entry.partition("="))
    if not sep or not name or not url:
        raise ValueError(f"SERVICES entry {entry!r} must look like name=url")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"service name {name!r} is longer than {MAX_NAME_LENGTH} characters")

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https", "tcp"):
        raise ValueError(f"service {name!r}: URL must start with http://, https:// or tcp://")
    if not parts.hostname or len(parts.hostname) > MAX_HOST_LENGTH:
        raise ValueError(f"service {name!r}: missing or overly long host in {url!r}")
    try:
        port = parts.port
    except ValueError:
        raise ValueError(f"service {name!r}: invalid port in {url!r}") from None
    if port is None:
        if scheme == "tcp":
            raise ValueError(f"service {name!r}: tcp:// URLs need a port, like tcp://ssh:22")
        port = DEFAULT_PORTS[scheme]
    if not 1 <= port <= 65535:
        raise ValueError(f"service {name!r}: port must be 1-65535")

    # url stays None for TCP services, so only HTTP services get a response-time check.
    return {"name": name, "host": parts.hostname, "port": port, "url": None if scheme == "tcp" else url}


def _parse_services(raw):
    """Turn "web=http://web:80/,ssh=tcp://ssh:22" into a list of service dicts."""
    services = [_parse_service(entry) for entry in raw.split(",") if entry.strip()]
    names = [s["name"] for s in services]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"duplicate service names in SERVICES: {', '.join(duplicates)}")
    if not 1 <= len(services) <= MAX_SERVICES:
        raise ValueError(f"SERVICES must list between 1 and {MAX_SERVICES} services")
    return services


# Unique identifier for this monitoring agent
AGENT_ID = os.environ.get("AGENT_ID", "").strip() or "agent-local"
if not AGENT_ID_PATTERN.fullmatch(AGENT_ID):
    raise ValueError(f"AGENT_ID {AGENT_ID!r} may only use letters, digits, '.', '_' and '-' (1-64 characters)")

# Central server address, without a trailing slash (reporter.py adds /report)
SERVER_URL = (os.environ.get("SERVER_URL", "").strip() or "http://127.0.0.1:8000").rstrip("/")
if urlsplit(SERVER_URL).scheme not in ("http", "https"):
    raise ValueError(f"SERVER_URL must start with http:// or https://, got {SERVER_URL!r}")

# Shared secret sent in the X-Agent-Token header
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip() or DEV_AGENT_TOKEN

# How often the agent sends reports (seconds)
REPORT_INTERVAL = _positive_int("REPORT_INTERVAL_S", 10)

# Which network interfaces count toward traffic: all, loopback, external, or one interface name
TRAFFIC_INTERFACE = os.environ.get("TRAFFIC_INTERFACE", "").strip() or "all"
if TRAFFIC_INTERFACE.lower() in ("all", "loopback", "external"):
    TRAFFIC_INTERFACE = TRAFFIC_INTERFACE.lower()  # keywords in any case; interface names stay exact

# Log of failed logins written by the target service (env/target_service.py)
AUTH_LOG_PATH = os.environ.get("AUTH_LOG_PATH", "").strip() or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "env", "logs", "auth.log"
)

# Services that the agent monitors. The default watches the server's own health check.
MONITORED_SERVICES = _parse_services(
    os.environ.get("SERVICES", "").strip() or "server=http://127.0.0.1:8000/health"
)

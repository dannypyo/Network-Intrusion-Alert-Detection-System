import ipaddress
import json
import os
from datetime import datetime

from config import AUTH_LOG_PATH

# The server's limits: a report breaking one is rejected whole
MAX_LOGINS_PER_REPORT = 1000
MAX_USERNAME_LENGTH = 128


def to_contract_entry(line):
    """
    Convert one log line into a failed-login entry for the report.

    The username and source IP come from the login request, so an attacker
    controls them. Anything that would break the contract is fixed or skipped
    here, because one bad entry would get the whole report rejected.

    Returns:
        {"user", "source_ip", "time"}, or None if the line is unusable.
    """
    try:
        record = json.loads(line)
        source_ip = str(ipaddress.ip_address(str(record["source_ip"]).strip()))
        time = datetime.fromisoformat(record["timestamp"])
        username = str(record.get("username") or "")
    except (ValueError, KeyError, TypeError, AttributeError):
        return None

    if time.tzinfo is None:
        # Without a timezone the time is ambiguous, and the server would reject it
        return None

    return {
        "user": username[:MAX_USERNAME_LENGTH] or "(empty)",
        "source_ip": source_ip,
        "time": time.isoformat()
    }


class FailedLoginReader:
    """
    Reads the failed logins the target service appends to its log, one JSON object per line.
    Each call returns only the entries added since the previous call.
    """

    def __init__(self, path):
        self.path = path
        self.position = 0     # bytes of the file already read
        self.file_id = None   # identifies the file, to notice it being replaced

        # Start at the end: entries from before the agent started are old attempts
        try:
            stats = os.stat(path)
            self.position, self.file_id = stats.st_size, stats.st_ino
        except OSError:
            pass  # no log yet: once it appears, everything in it is new

    def read_lines(self):
        """Return the complete lines added since the last call."""
        try:
            with open(self.path, "rb") as log:
                stats = os.fstat(log.fileno())
                if stats.st_ino != self.file_id or stats.st_size < self.position:
                    # The log was replaced or cleared, so read the new one from the start
                    self.position, self.file_id = 0, stats.st_ino
                log.seek(self.position)
                data = log.read()
        except FileNotFoundError:
            self.position, self.file_id = 0, None
            return []

        # Stop at the last newline: a line still being written waits for the next call
        end = data.rfind(b"\n")
        if end == -1:
            return []
        self.position += end + 1
        return [line for line in data[:end].split(b"\n") if line.strip()]

    def read_new(self):
        """Return the new failed logins, ready for the report."""
        entries = []
        skipped = 0
        for line in self.read_lines():
            entry = to_contract_entry(line)
            if entry is None:
                skipped += 1
            else:
                entries.append(entry)

        if skipped:
            print(f"Skipped {skipped} unreadable failed-login entr{'y' if skipped == 1 else 'ies'}.")

        if len(entries) > MAX_LOGINS_PER_REPORT:
            # Keep the most recent ones: detection only looks at the last 60 seconds
            print(f"Sending the latest {MAX_LOGINS_PER_REPORT} of {len(entries)} failed logins.")
            entries = entries[-MAX_LOGINS_PER_REPORT:]

        return entries


# One reader for the whole agent, created when the agent starts
_reader = FailedLoginReader(AUTH_LOG_PATH)


def read_new_failed_logins():
    """Failed logins added to the log since the last report."""
    return _reader.read_new()

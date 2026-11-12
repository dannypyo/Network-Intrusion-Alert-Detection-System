from datetime import datetime, timezone
from typing import List, Dict, Any

# Rule Thresholds
FAILED_LOGIN_THRESHOLD = 5  # Alert on MORE than this many failed logins in the window
FAILED_LOGIN_WINDOW_S = 60
TRAFFIC_BYTES_THRESHOLD = 1000000  
RESPONSE_TIME_THRESHOLD_MS = 1000.0

class DetectionEngine:
    def __init__(self):
        self.failed_login_history: Dict[str, List[datetime]] = {}
        self.service_downtime_counts: Dict[tuple, int] = {}

    def evaluate_report(self, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts = []
        agent_id = report.get("agent_id")
        timestamp_str = report.get("timestamp")
        report_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

        # 1. Brute-force / Failed Logins check
        # Record every login in this report first, then check each IP once,
        # so one report raises at most one alert per IP.
        reported_ips = set()
        for login in report.get("failed_logins", []):
            ip = login.get("source_ip")
            if ip:
                if ip not in self.failed_login_history:
                    self.failed_login_history[ip] = []
                self.failed_login_history[ip].append(report_time)
                reported_ips.add(ip)

        for ip in sorted(reported_ips):
            # Keep timestamps within the window
            self.failed_login_history[ip] = [
                t for t in self.failed_login_history[ip]
                if (report_time - t).total_seconds() <= FAILED_LOGIN_WINDOW_S
            ]

            # The server deduplicates repeated alerts by their key
            if len(self.failed_login_history[ip]) > FAILED_LOGIN_THRESHOLD:
                alerts.append({
                    "key": f"BRUTE_FORCE_LOGIN:{agent_id}:{ip}",
                    "agent_id": agent_id,
                    "type": "BRUTE_FORCE_LOGIN",
                    "severity": "HIGH",
                    "message": f"More than {FAILED_LOGIN_THRESHOLD} failed logins from IP {ip} within {FAILED_LOGIN_WINDOW_S}s."
                })

        # 2. Traffic Spike check
        traffic = report.get("traffic", {})
        interval = traffic.get("interval_s", 10)
        total_bps = (traffic.get("bytes_in", 0) + traffic.get("bytes_out", 0)) / interval if interval > 0 else 0
        if total_bps > TRAFFIC_BYTES_THRESHOLD:
            alerts.append({
                "key": f"TRAFFIC_SPIKE:{agent_id}",
                "agent_id": agent_id,
                "type": "TRAFFIC_SPIKE",
                "severity": "MEDIUM",
                "message": f"High traffic rate detected: {total_bps:.2f} bytes/sec."
            })

        # 3. Services check (Latency & Availability)
        for svc in report.get("services", []):
            svc_key = (agent_id, svc.get("name"))
            
            # response_ms is null when the service gave no response at all
            response_ms = svc.get("response_ms")
            if response_ms is not None and response_ms > RESPONSE_TIME_THRESHOLD_MS:
                alerts.append({
                    "key": f"HIGH_LATENCY:{agent_id}:{svc.get('name')}",
                    "agent_id": agent_id,
                    "type": "HIGH_LATENCY",
                    "severity": "LOW",
                    "message": f"Service '{svc.get('name')}' response time is {svc.get('response_ms')}ms."
                })

            if not svc.get("up", True):
                self.service_downtime_counts[svc_key] = self.service_downtime_counts.get(svc_key, 0) + 1
                if self.service_downtime_counts[svc_key] >= 2:
                    alerts.append({
                        "key": f"SERVICE_DOWN:{agent_id}:{svc.get('name')}",
                        "agent_id": agent_id,
                        "type": "SERVICE_DOWN",
                        "severity": "HIGH",
                        "message": f"Service '{svc.get('name')}' has been down for 2 consecutive checks."
                    })
            else:
                self.service_downtime_counts[svc_key] = 0

        return alerts
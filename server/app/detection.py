from datetime import datetime, timezone
from typing import List, Dict, Any

# Threshold configurations
FAILED_LOGIN_THRESHOLD = 5
FAILED_LOGIN_WINDOW_S = 60
TRAFFIC_BYTES_THRESHOLD = 1000000  # Example: 1 MB/s
RESPONSE_TIME_THRESHOLD_MS = 1000.0

class DetectionEngine:
    def __init__(self):
        # Keep track of recent failed logins for windowed counting: {ip: [timestamps]}
        self.failed_login_history: Dict[str, List[datetime]] = {}
        # Track consecutive service failures: {(agent_id, service_name): count}
        self.service_downtime_counts: Dict[tuple, int] = {}

    def evaluate_report(self, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts = []
        agent_id = report.get("agent_id")
        timestamp_str = report.get("timestamp")
        report_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

        # 1. Check Failed Logins
        failed_logins = report.get("failed_logins", [])
        for login in failed_logins:
            ip = login.get("source_ip")
            if ip:
                if ip not in self.failed_login_history:
                    self.failed_login_history[ip] = []
                self.failed_login_history[ip].append(report_time)
                
                # Filter timestamps within the 60s window
                self.failed_login_history[ip] = [
                    t for t in self.failed_login_history[ip] 
                    if (report_time - t).total_seconds() <= FAILED_LOGIN_WINDOW_S
                ]
                
                if len(self.failed_login_history[ip]) >= FAILED_LOGIN_THRESHOLD:
                    alerts.append({
                        "agent_id": agent_id,
                        "type": "BRUTE_FORCE_SSH",
                        "severity": "HIGH",
                        "message": f"Over {FAILED_LOGIN_THRESHOLD} failed logins from IP {ip} within {FAILED_LOGIN_WINDOW_S}s."
                    })

        # 2. Check Traffic Spikes
        traffic = report.get("traffic", {})
        interval = traffic.get("interval_s", 10)
        bytes_in = traffic.get("bytes_in", 0)
        bytes_out = traffic.get("bytes_out", 0)
        total_bps = (bytes_in + bytes_out) / interval if interval > 0 else 0
        
        if total_bps > TRAFFIC_BYTES_THRESHOLD:
            alerts.append({
                "agent_id": agent_id,
                "type": "TRAFFIC_SPIKE",
                "severity": "MEDIUM",
                "message": f"High traffic rate detected: {total_bps:.2f} bytes/sec."
            })

        # 3. Check Services (Response Time & Availability)
        services = report.get("services", [])
        for svc in services:
            svc_key = (agent_id, svc.get("name"))
            
            # Response time check
            if svc.get("response_ms", 0) > RESPONSE_TIME_THRESHOLD_MS:
                alerts.append({
                    "agent_id": agent_id,
                    "type": "HIGH_LATENCY",
                    "severity": "LOW",
                    "message": f"Service '{svc.get('name')}' response time is {svc.get('response_ms')}ms."
                })

            # Availability check (2 checks in a row down)
            if not svc.get("up", True):
                self.service_downtime_counts[svc_key] = self.service_downtime_counts.get(svc_key, 0) + 1
                if self.service_downtime_counts[svc_key] >= 2:
                    alerts.append({
                        "agent_id": agent_id,
                        "type": "SERVICE_DOWN",
                        "severity": "HIGH",
                        "message": f"Service '{svc.get('name')}' has been down for 2 consecutive checks."
                    })
            else:
                # Reset counter if service is back up
                self.service_downtime_counts[svc_key] = 0

        return alerts
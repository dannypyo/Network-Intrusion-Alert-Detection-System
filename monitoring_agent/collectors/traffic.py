import ipaddress
from collections import namedtuple

import psutil

from config import TRAFFIC_INTERFACE

# The same four totals psutil reports, so calculate_network_traffic works unchanged
TrafficTotals = namedtuple("TrafficTotals", "bytes_recv bytes_sent packets_recv packets_sent")

KEYWORDS = ("all", "loopback", "external")


def is_loopback(name, addresses):
    """
    True if the interface has a loopback address (127.0.0.1 or ::1).
    Checking the address works on every system; the name differs
    (lo on Linux, lo0 on macOS, "Loopback Pseudo-Interface 1" on Windows).
    """
    for address in addresses.get(name, []):
        try:
            if ipaddress.ip_address(address.address.split("%")[0]).is_loopback:
                return True
        except ValueError:
            continue  # MAC addresses and other entries that are not IP addresses
    return False


def select_interfaces(counters):
    """
    Return the names of the interfaces that TRAFFIC_INTERFACE asks for.
    """
    if TRAFFIC_INTERFACE == "all":
        return list(counters)

    addresses = psutil.net_if_addrs()
    if TRAFFIC_INTERFACE == "loopback":
        return [name for name in counters if is_loopback(name, addresses)]
    if TRAFFIC_INTERFACE == "external":
        return [name for name in counters if not is_loopback(name, addresses)]

    return [TRAFFIC_INTERFACE] if TRAFFIC_INTERFACE in counters else []


def get_network_snapshot():
    """
    Get the current cumulative network statistics for the interfaces
    chosen by TRAFFIC_INTERFACE.

    These values represent totals, not just the latest interval.
    Interfaces are chosen again each time, so one that appears later
    (a VPN, a Docker network) is included automatically.
    """
    counters = psutil.net_io_counters(pernic=True)
    chosen = [counters[name] for name in select_interfaces(counters)]

    return TrafficTotals(*(
        sum(getattr(interface, field) for interface in chosen)
        for field in TrafficTotals._fields
    ))


def calculate_network_traffic(previous_stats, current_stats):
    """
    Calculate the network traffic that occurred between two snapshots.
    """

    return {
        "bytes_in": max(0, current_stats.bytes_recv - previous_stats.bytes_recv),
        "bytes_out": max(0, current_stats.bytes_sent - previous_stats.bytes_sent),
        "packets_in": max(0, current_stats.packets_recv - previous_stats.packets_recv),
        "packets_out": max(0, current_stats.packets_sent - previous_stats.packets_sent)
    }


def check_traffic_interface():
    """
    Check TRAFFIC_INTERFACE when the agent starts, so a typo stops it right away.
    """
    counters = psutil.net_io_counters(pernic=True)

    if TRAFFIC_INTERFACE not in KEYWORDS and TRAFFIC_INTERFACE not in counters:
        raise ValueError(
            f"TRAFFIC_INTERFACE {TRAFFIC_INTERFACE!r} was not found. "
            f"Interfaces on this machine: {', '.join(sorted(counters))}"
        )

    if not select_interfaces(counters):
        print(f"Warning: no {TRAFFIC_INTERFACE} network interfaces found; traffic will read 0")


check_traffic_interface()

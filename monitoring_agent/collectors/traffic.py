import psutil


def get_network_snapshot():
    """
    Get the current cumulative network statistics.

    These values represent totals, not just the latest interval.
    """
    return psutil.net_io_counters()


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
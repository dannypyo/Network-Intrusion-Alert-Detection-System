import time

from collectors.traffic import (
    get_network_snapshot,
    calculate_network_traffic
)

print("Taking first network snapshot...")

# Record the starting network counters
previous_stats = get_network_snapshot()

print("Waiting 5 seconds for network activity...")

# Wait to give the computer time to send and receive data
time.sleep(5)

print("Taking second network snapshot...")

# Record the new network counters
current_stats = get_network_snapshot()

# Calculate the difference between the two snapshots
traffic = calculate_network_traffic(previous_stats, current_stats)

print("\nNetwork traffic during the 5-second test:")
print(traffic)
from collectors.availability import check_service_availability

host = "google.com"
port = 443

is_available = check_service_availability(host, port)

if is_available:
    print(f"{host}:{port} is available.")
else:
    print(f"{host}:{port} is unavailable.")
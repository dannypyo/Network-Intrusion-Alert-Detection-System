from collectors.availability import check_service_availability

host = "google.com"
port = 443

result = check_service_availability(host, port)

if result["up"]:
    print(f"{host}:{port} is available ({result['response_ms']} ms to connect).")
else:
    print(f"{host}:{port} is unavailable ({result['error']}).")
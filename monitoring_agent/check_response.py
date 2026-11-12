from collectors.response import get_response_time

url = "https://www.google.com"

result = get_response_time(url)

if result["up"]:
    print(f"Response time: {result['response_ms']} ms")
else:
    print(f"Service is down ({result['error']}), response time: {result['response_ms']} ms")
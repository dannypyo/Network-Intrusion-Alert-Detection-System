from collectors.response import get_response_time

url = "https://www.google.com"

response_time = get_response_time(url)

if response_time is not None:
    print(f"Response time: {response_time} ms")
else:
    print("Server did not respond.")
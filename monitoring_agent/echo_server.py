
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class TestHandler(BaseHTTPRequestHandler):

    def do_POST(self):

        # Only accept requests to /report
        if self.path != "/report":
            self.send_error(404, "Not Found")
            return

        # Determine how many bytes were sent
        content_length = int(self.headers.get("Content-Length", 0))

        # Read the incoming JSON request
        raw_data = self.rfile.read(content_length)

        try:
            report = json.loads(raw_data)

        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400, "Invalid JSON")
            return

        # Print the report received from the agent
        print("\nReceived report:")
        print(json.dumps(report, indent=4), flush=True)

        # Respond with HTTP 200 OK
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "received"}')


def main():
    server = HTTPServer(("127.0.0.1", 8765), TestHandler)

    print("Test server listening on http://127.0.0.1:8765", flush=True)

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print("\nStopping test server.")

    finally:
        server.server_close()


if __name__ == "__main__":
    main()

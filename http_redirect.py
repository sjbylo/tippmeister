"""Tiny HTTP server that redirects all requests to HTTPS."""

import os
from http.server import HTTPServer, BaseHTTPRequestHandler

HTTPS_PORT = os.environ.get('PORT', '9443')


class RedirectHandler(BaseHTTPRequestHandler):
	def do_GET(self):
		host = self.headers.get('Host', 'localhost').split(':')[0]
		self.send_response(301)
		self.send_header('Location', f'https://{host}:{HTTPS_PORT}{self.path}')
		self.end_headers()

	do_POST = do_GET
	do_HEAD = do_GET

	def log_message(self, format, *args):
		pass  # suppress access logs


if __name__ == '__main__':
	server = HTTPServer(('0.0.0.0', 8080), RedirectHandler)
	print("HTTP->HTTPS redirect listening on port 8080")
	server.serve_forever()

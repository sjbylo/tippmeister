"""Entrypoint for distroless container -- generates self-signed cert if needed, then starts gunicorn."""
import os
import subprocess
import sys

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CERT_DIR = os.path.join(DATA_DIR, "certs")
CERT_FILE = os.path.join(CERT_DIR, "cert.pem")
KEY_FILE = os.path.join(CERT_DIR, "key.pem")
PORT = os.environ.get("PORT", "9443")

os.makedirs(CERT_DIR, exist_ok=True)

if not os.path.exists(CERT_FILE) or not os.path.exists(KEY_FILE):
	print("Generating self-signed TLS certificate...")
	from cryptography import x509
	from cryptography.x509.oid import NameOID
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import rsa
	from datetime import datetime, timedelta

	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	subject = issuer = x509.Name([
		x509.NameAttribute(NameOID.COMMON_NAME, "tippmeister"),
		x509.NameAttribute(NameOID.ORGANIZATION_NAME, "DerTippmeister"),
	])
	import ipaddress
	cert = (
		x509.CertificateBuilder()
		.subject_name(subject)
		.issuer_name(issuer)
		.public_key(key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(datetime.utcnow())
		.not_valid_after(datetime.utcnow() + timedelta(days=365))
		.add_extension(
			x509.SubjectAlternativeName([
				x509.DNSName("localhost"),
				x509.DNSName("tippmeister"),
				x509.DNSName("bastion"),
				x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
			]),
			critical=False,
		)
		.sign(key, hashes.SHA256())
	)
	with open(KEY_FILE, "wb") as f:
		f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
	os.chmod(KEY_FILE, 0o644)
	with open(CERT_FILE, "wb") as f:
		f.write(cert.public_bytes(serialization.Encoding.PEM))
	print(f"Certificate generated: {CERT_FILE}, {KEY_FILE}")
else:
	print(f"Using existing certificates in {CERT_DIR}")

print(f"=== Der Tippmeister ===")
print(f"Starting on port {PORT} (HTTPS) + 8080 (HTTP redirect)")
print(f"Invite token: {os.environ.get('INVITE_TOKEN', 'check logs')}")
print(f"========================")

# Start HTTP->HTTPS redirect in background
subprocess.Popen([sys.executable, "/app/http_redirect.py"])

# Start gunicorn with TLS
os.execvp("gunicorn", [
	"gunicorn", "wsgi:application",
	"--bind", f"0.0.0.0:{PORT}",
	"--certfile", CERT_FILE,
	"--keyfile", KEY_FILE,
	"--workers", "2",
	"--preload",
	"--timeout", "120",
	"--access-logfile", "-",
	"--error-logfile", "-",
])

# Stage 1: Build -- install dependencies using the builder image (has shell + pip)
FROM registry.access.redhat.com/hi/python:3.13-builder AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/tmp/install -r requirements.txt

# Stage 2: Runtime -- distroless, hardened, near-zero CVEs
FROM registry.access.redhat.com/hi/python:3.13

WORKDIR /app

COPY --from=builder /tmp/install /usr/local
COPY . /app

ENV DATA_DIR=/data
ENV PORT=9443
VOLUME /data

EXPOSE 9443
EXPOSE 8080

ENTRYPOINT ["python3", "/app/entrypoint.py"]

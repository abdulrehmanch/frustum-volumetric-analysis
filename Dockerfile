FROM python:3.12-slim

# Prevent python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install pandas with network retry and timeout
RUN pip install --default-timeout=120 --retries 5 --no-cache-dir pandas

# Copy scripts and viewer template
COPY scripts/ /app/scripts/

# Create mount targets for outputs and inputs
RUN mkdir -p /app/outputs /app/inputs

EXPOSE 8080

CMD ["python3", "scripts/serve_portal.py", "--port", "8080"]

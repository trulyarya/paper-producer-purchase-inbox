FROM python:3.13.9-slim

# Silence interactive apt-get prompts during Docker build (complaining about no UI)
ENV DEBIAN_FRONTEND=noninteractive

# Minimal system dependencies for WeasyPrint HTML-to-PDF conversion:
    # ca-certificates: SSL certificates for HTTPS requests
    # libcairo2: Core 2D graphics rendering engine
    # libpango-1.0-0: Text layout and internationalization
    # libpangocairo-1.0-0: Pango+Cairo integration for text rendering
    # libgdk-pixbuf-2.0-0: Image loading (required for CSS gradients/backgrounds)
    # libglib2.0-0: GLib utilities required by Pango
    # fonts-dejavu: Standard sans-serif/serif/mono fonts for PDF text

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      libcairo2 \
      libpango-1.0-0 \
      libpangocairo-1.0-0 \
      libgdk-pixbuf-2.0-0 \
      libglib2.0-0 \
      fonts-dejavu \
 && rm -rf /var/lib/apt/lists/*

# Run the app as an unprivileged user for better security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching
COPY requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the repo (source, infra docs, Gmail credentials folder, etc.)
COPY . .

# Give the non-root user ownership of /app and /app/cred for token writes
RUN chown -R appuser:appuser /app

USER appuser

# Start the asynchronous Gmail polling loop defined in main.py
CMD ["python", "main.py"]

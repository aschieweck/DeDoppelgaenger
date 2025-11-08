FROM python:3.13-slim

# Install runtime dependencies for Pillow and libraw for rawpy
RUN apt-get update && apt-get install -y --no-install-recommends \
      libjpeg62-turbo \
      zlib1g \
      liblcms2-2 \
      libopenjp2-7 \
      libtiff6 \
      libwebp7 \
      libraw23 \
      && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements first (better cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your script
COPY dedoppelgaenger.py .

# Default command
ENTRYPOINT ["python", "dedoppelgaenger.py"]


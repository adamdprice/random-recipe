# Kinly Lead Distribution - Flask backend + frontend static
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .
RUN mkdir -p data frontend/images

# Railway sets PORT
ENV PORT=3000
EXPOSE 3000
CMD ["sh", "-c", "gunicorn -w 1 -b 0.0.0.0:${PORT} app:app"]

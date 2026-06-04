FROM python:3.13-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Create data directory
RUN mkdir -p /app/data

EXPOSE 5000

# Run with gunicorn + scheduler
CMD ["sh", "-c", "python scheduler.py & gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app"]

FROM python:3.9-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV APP_NAME CoreText

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Expose port
ENV PORT 8080

# Run application
CMD exec gunicorn --bind : --workers 1 --threads 8 --timeout 0 wsgi:app

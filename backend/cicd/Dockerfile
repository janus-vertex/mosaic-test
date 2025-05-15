# Use official Python runtime as a parent image
FROM python:3.12-slim

# Set working directory in the container
WORKDIR /app/backend
ENV PYTHONPATH=/app/backend

# Copy requirements first to leverage Docker cache
COPY ./backend/requirements/requirements.txt .

# Install dependencies
# Update package lists and install required system dependencies:
# - libpq-dev: PostgreSQL client development files needed for psycopg2 (PostgreSQL adapter for Python)
# - python3-dev: Python development headers required for compiling certain Python packages with C extensions
RUN apt-get update && apt-get install -y libpq-dev python3-dev build-essential
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY ./backend/ .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
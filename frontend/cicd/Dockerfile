# Use Python base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app/frontend
ENV PYTHONPATH=/app/frontend

# Copy requirements first to leverage Docker cache
COPY ./frontend/requirements/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY ./frontend/ .

# Expose the Streamlit port
EXPOSE 8501

# Command to run the application
CMD ["streamlit", "run", "app.py"]

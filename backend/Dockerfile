# Stage 1: The "builder" stage to install dependencies
# This creates a lean and optimized final image.
FROM python:3.10-slim as builder

WORKDIR /app

# Install system dependencies that might be needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential

# Copy only the requirements file first to leverage Docker's layer caching
COPY requirements.txt .

# Create a virtual environment and install dependencies into it
# Using wheels makes the final installation faster
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt


# Stage 2: The final "runtime" stage
FROM python:3.10-slim

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Set the PATH to include the venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy your application source code and credentials
# IMPORTANT: This copies your service account key into the image.
# We will show a better, more secure method during Cloud Run deployment.
COPY . .

# Tell Docker that your application listens on port 8000
# Cloud Run will automatically use the $PORT environment variable.
EXPOSE 8080

# The command to run your application
# Uses the $PORT variable provided by Cloud Run for flexibility.
# --host 0.0.0.0 is crucial to make the app accessible from outside the container.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

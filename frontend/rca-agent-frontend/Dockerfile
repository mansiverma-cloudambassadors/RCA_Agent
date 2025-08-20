# Stage 1: Build frontend
FROM node:18 as builder

WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Serve static files using Python HTTP server
FROM python:3.10-slim

WORKDIR /app

# Copy built frontend files
COPY --from=builder /app/build ./build

# Cloud Run will inject PORT (default: 8080)
ENV PORT=8080

EXPOSE 8080

# Start Python HTTP server to serve static files
CMD ["serve", "-s", "build", "-l", "0.0.0.0:${PORT}"]

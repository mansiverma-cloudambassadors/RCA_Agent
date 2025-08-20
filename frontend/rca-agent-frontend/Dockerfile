# Stage 1: Build React app
FROM node:18 as builder

WORKDIR /app

# Copy only package files first (better caching)
COPY package*.json ./
RUN npm install

# Copy the rest of the project
COPY . .
RUN npm run build

# Stage 2: Serve React build
FROM node:18

WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/build ./build

ENV PORT=8080
EXPOSE 8080

CMD ["serve", "-s", "build", "-l", "8080"]

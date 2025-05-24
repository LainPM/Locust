# Use the official Rust image
FROM rust:1.75 as builder

# Set the working directory
WORKDIR /app

# Copy the Cargo.toml and Cargo.lock files
COPY Cargo.toml ./

# Copy the source code
COPY src ./src

# Build the application in release mode
RUN cargo build --release

# Use a minimal runtime image
FROM debian:bookworm-slim

# Install necessary runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the binary from the builder stage
COPY --from=builder /app/target/release/axis-bot /usr/local/bin/axis-bot

# Set the binary as executable
RUN chmod +x /usr/local/bin/axis-bot

# Run the bot
CMD ["axis-bot"]

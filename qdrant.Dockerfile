FROM qdrant/qdrant:latest

# Switch to root user to install packages and manage users
USER root

# Ensure 'qdrant' group and user exist with UID/GID 1000.
# This is important if the qdrant entrypoint script tries to use the name 'qdrant'.
# Using --system for service accounts and --no-create-home as it's not a login user.
RUN if ! getent group qdrant > /dev/null; then addgroup --system --gid 1000 qdrant; fi && \
    if ! getent passwd qdrant > /dev/null; then adduser --system --uid 1000 --gid 1000 --no-create-home --disabled-password --gecos "Qdrant Service User" qdrant; fi

# Update package lists and install curl
# The qdrant/qdrant:latest image is based on Debian, so we use apt-get
RUN apt-get update && \
    apt-get install -y curl gosu && \
    rm -rf /var/lib/apt/lists/*

# Copy Qdrant configuration. Qdrant will load this automatically.
COPY qdrant_config.yaml /qdrant/config/config.yaml
RUN chown 1000:1000 /qdrant/config/config.yaml # Ensure qdrant user can read it

# Copy the custom entrypoint script and make it executable
COPY qdrant_entrypoint.sh /usr/local/bin/qdrant_entrypoint.sh
RUN chmod +x /usr/local/bin/qdrant_entrypoint.sh

# Set the custom entrypoint
# This script will run as root, and then drop privileges for the Qdrant process.
ENTRYPOINT ["/usr/local/bin/qdrant_entrypoint.sh"]
# The CMD from the base image (qdrant/qdrant:latest) will be passed as arguments to this entrypoint.

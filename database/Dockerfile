# Use the official PostgreSQL image as a base image
FROM postgres:14-alpine

# Set environment variables from .env
ENV POSTGRES_USER=$POSTGRES_USER
ENV POSTGRES_PASSWORD=$POSTGRES_PASSWORD
ENV POSTGRES_DB=$POSTGRES_DB

# Expose the PostgreSQL port
EXPOSE 5432

# Copy initialization script (optional, for creating tables/roles)
COPY init.sql /docker-entrypoint-initdb.d/

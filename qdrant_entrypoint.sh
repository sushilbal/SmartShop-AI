#!/bin/sh
set -e

# Ensure the Qdrant base directory is writable by the qdrant user if it's not already.
# This is for files Qdrant might try to write in its WORKDIR, like the init indicator.
if [ "$(stat -c %u /qdrant)" != "1000" ] || [ "$(stat -c %g /qdrant)" != "1000" ]; then
  echo "Changing ownership of /qdrant to qdrant:qdrant (1000:1000)"
  chown 1000:1000 /qdrant # No -R needed if it's just the directory itself for an indicator file
fi

# Ensure the storage directory is owned by the qdrant user (UID 1000, GID 1000)
# This runs at container startup, after the volume is mounted.
# Check if the directory is already owned by qdrant to avoid unnecessary chown on every start
if [ "$(stat -c %u /qdrant/storage)" != "1000" ] || [ "$(stat -c %g /qdrant/storage)" != "1000" ]; then
  echo "Changing ownership of /qdrant/storage to qdrant:qdrant (1000:1000)"
  chown -R 1000:1000 /qdrant/storage
else
  echo "/qdrant/storage ownership is already correct."
fi

# Execute the original Qdrant entrypoint script, passing along any arguments
# The original entrypoint for qdrant/qdrant:latest is /entrypoint.sh
echo "Dropping privileges and executing original Qdrant entrypoint as user 'qdrant': /qdrant/entrypoint.sh $@"
exec gosu qdrant /qdrant/entrypoint.sh "$@"

# Use a minimal base image
FROM python:3.10-alpine

# Set the working directory
WORKDIR /app

COPY --from=repo pyproject.toml /tmp/deception_runtime/
COPY --from=repo deception_runtime/ /tmp/deception_runtime/deception_runtime/
COPY --from=repo deceptions/ /app/deceptions/

# Copy the challenge files
COPY ./src/ /app/
COPY ./requirements.txt /app/requirements.txt

# Set the flag
ENV FLAG=CTF{REDACTED}

# Create a nonroot user
RUN adduser -D nonroot && \
    chown nonroot /app

# Install required packages
RUN apk add --update --no-cache build-base linux-headers libxml2-dev libxslt-dev && \
    pip install --no-cache-dir /tmp/deception_runtime && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del build-base linux-headers libxml2-dev libxslt-dev

# Switch to the nonroot user
USER nonroot

# Run the challenge script
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--error-logfile=/dev/null", "app:app"]

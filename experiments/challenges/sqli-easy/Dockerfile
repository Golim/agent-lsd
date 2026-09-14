# Use a minimal base image
FROM python:3.13-alpine

# Set the working directory
WORKDIR /app

# Copy the local runtime and generated deception assets
COPY --from=repo pyproject.toml /tmp/deception_runtime/
COPY --from=repo deception_runtime/ /tmp/deception_runtime/deception_runtime/
COPY --from=repo deceptions/ /app/deceptions/

# Copy the challenge files
COPY ./src/ /app/
COPY requirements.txt /app
COPY ./flag.txt /

# Set the flag
ENV FLAG=CTF{REDACTED}

# Create a nonroot user
RUN adduser -D nonroot && \
    chown nonroot /app

# Install required packages
RUN apk add --update --no-cache build-base linux-headers oath-toolkit-oathtool procps && \
    pip install --no-cache-dir /tmp/deception_runtime && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del build-base linux-headers

# Switch to the nonroot user
USER nonroot

# Run the challenge script
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--error-logfile=/dev/null", "app:app"]

# Use a minimal base image
FROM python:3.10-alpine

# Set the working directory
WORKDIR /app

# Copy the local runtime and generated deception assets
COPY --from=repo pyproject.toml /tmp/deception_runtime/
COPY --from=repo deception_runtime/ /tmp/deception_runtime/deception_runtime/
COPY --from=repo deceptions/ /app/deceptions/

# Copy the challenge files
COPY ./src/ /app/

# Copy the flag
COPY ./flag.txt /app/flag.txt

# Environment variables
# ENV DENYLIST=`$

# Make the /app directory not writeable
RUN chmod a-w /app

# Create a nonroot user
RUN adduser -D nonroot && \
    chown nonroot /app

# Make the /static directory writeable
RUN mkdir /app/static && \
    chown nonroot /app/static

# Install required packages
RUN apk add --update --no-cache \
    build-base \
    zlib-dev \
    libffi-dev \
    libxml2-dev \
    libxslt-dev \
    && pip install --no-cache-dir /tmp/deception_runtime \
    && pip install --no-cache-dir -r requirements.txt

# Switch to the nonroot user
USER nonroot

# Expose the port from the environment variable
EXPOSE 5000

# Run the challenge script
CMD ["python", "calculator.py"]

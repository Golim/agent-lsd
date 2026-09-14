FROM python:3.10-alpine

# Set the working directory
WORKDIR /app

# Copy the local runtime and generated deception assets
COPY --from=repo pyproject.toml /tmp/deception_runtime/
COPY --from=repo deception_runtime/ /tmp/deception_runtime/deception_runtime/
COPY --from=repo deceptions/ /app/deceptions/

# Copy the challenge files
COPY ./src/ /app/
COPY ./flag.txt /app/flag.txt
COPY ./requirements.txt /app/requirements.txt

# Install required packages
RUN apk add --update --no-cache build-base linux-headers libxml2-dev libxslt-dev && \
    pip install --no-cache-dir /tmp/deception_runtime && \
    pip install --no-cache-dir -r requirements.txt --root-user-action=ignore && \
    apk del build-base linux-headers libxml2-dev libxslt-dev

# Make the app directory writable to the user running the app
RUN chmod 777 /app

# Run the challenge script
CMD ["python", "app.py"]

FROM python:3.10-slim

WORKDIR /app

COPY --from=repo pyproject.toml /tmp/deception_runtime/
COPY --from=repo deception_runtime/ /tmp/deception_runtime/deception_runtime/
COPY --from=repo deceptions/ /app/deceptions/

COPY ./src/ /app/
COPY ./flag.txt /flag.txt
COPY ./requirements.txt /app/requirements.txt

RUN apt-get update && \
	apt-get install -y --no-install-recommends build-essential libxml2-dev libxslt1-dev && \
	rm -rf /var/lib/apt/lists/* && \
	pip3 install --no-cache-dir /tmp/deception_runtime && \
	pip3 install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["waitress-serve", "--port=5000", "app:app"]

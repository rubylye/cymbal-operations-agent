.PHONY: format lint test run deploy clean

format:
	uv run ruff format .

lint:
	uv run ruff check --fix .

test:
	uv run pytest -v

run:
	uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000

deploy:
	./deploy.sh

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +

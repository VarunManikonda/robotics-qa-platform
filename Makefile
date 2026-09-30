.PHONY: setup test lint serve demo docker clean

setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt

# each package is tested from its own directory (their test packages share a name)
test:
	cd dashboard && python3 -m pytest -q
	cd cobot_qa  && python3 -m pytest -q
	cd amr_health && python3 -m pytest -q

lint:
	ruff check .

serve:
	cd dashboard && uvicorn app.main:create_app --factory --port 8000

demo:
	python3 scripts/demo_offline.py --url http://127.0.0.1:8000 --plot docs/amr_detection.png

docker:
	docker build -t robotics-qa-dashboard . && docker run --rm -p 8000:8000 robotics-qa-dashboard

clean:
	find . -name __pycache__ -prune -exec rm -rf {} + ; rm -rf .pytest_cache .ruff_cache

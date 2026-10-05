.PHONY: help install test lint format clean dashboard

# Default target
help:
	@echo "OpsMind Development Commands"
	@echo "==========================="
	@echo ""
	@echo "  install     Install package in development mode"
	@echo "  test        Run tests"
	@echo "  lint        Run linter"
	@echo "  format      Format code with black"
	@echo "  dashboard   Launch Streamlit dashboard on localhost:8501"
	@echo "  clean       Clean up build artifacts"
	@echo ""

# Installation
install:
	pip install -e ".[dev]"

# Testing
test:
	@echo "🧪 Running tests..."
	python tests/test_opsmind.py

# Code quality
lint:
	@echo "🔍 Running linter..."
	flake8 opsmind/ tests/ examples/

format:
	@echo "🎨 Formatting code..."
	black opsmind/ tests/ examples/

# Cleanup
clean:
	@echo "🧹 Cleaning up..."
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Dashboard
dashboard:
	@echo "🚀 Launching OpsMind Dashboard..."
	streamlit run dashboard/app.py --server.port 8501
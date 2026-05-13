import sys
import os

# Point tests at an in-memory SQLite DB so they never touch jobs_search.db
os.environ.setdefault("DB_URL", "sqlite:///:memory:")

# Tests must be deterministic and offline: disable OpenAI calls even if the
# developer has OPENAI_API_KEY in their environment.
os.environ.setdefault("OPENAI_CV_PARSER", "0")
os.environ.setdefault("OPENAI_CV_CLASSIFIER", "0")

# Add the project root to sys.path so all imports work without __init__.py files.
# pytest loads this file automatically before running any tests.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

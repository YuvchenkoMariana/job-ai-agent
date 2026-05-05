import sys
import os

# Point tests at an in-memory SQLite DB so they never touch jobs_search.db
os.environ.setdefault("DB_URL", "sqlite:///:memory:")

# Add the project root to sys.path so all imports work without __init__.py files.
# pytest loads this file automatically before running any tests.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

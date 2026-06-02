"""
One-shot script to initialise dev.db by running all Alembic migrations
programmatically — no CLI needed.
"""
import os
import sys

# Change to backend directory so relative paths in alembic.ini work
backend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(backend_dir)

# Make sure we can import app modules
sys.path.insert(0, backend_dir)

from alembic.config import Config
from alembic import command

alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
print("Running alembic upgrade head...")
command.upgrade(alembic_cfg, "head")
print("Done — dev.db is up to date.")

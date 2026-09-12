"""Keep tests deterministic even when a developer has enabled local models in .env."""

import os

os.environ["ENABLE_LOCAL_MODELS"] = "false"
os.environ["RAG_MODE"] = "local"
os.environ["USE_MOCK_PROVIDERS"] = "true"

import os
import sys
import tempfile
from pathlib import Path

# Keep tests in an isolated temporary database and storage directory. This
# prevents the integration suite from polluting the Project ORION development
# database that the Hypothesis Lab uses for its synthetic scenarios.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="orion-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(_TEST_ROOT / "evidence_storage")

sys.path.insert(0, str(Path(__file__).parents[1]))

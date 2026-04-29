import pytest
from pathlib import Path
import shutil
import tempfile

@pytest.fixture
def temp_vault():
    """Fixture to create a temporary vault structure."""
    tmp_dir = Path(tempfile.mkdtemp())
    (tmp_dir / "notes").mkdir()
    (tmp_dir / "literature").mkdir()
    (tmp_dir / "annotations").mkdir()
    (tmp_dir / "attachments").mkdir()
    (tmp_dir / ".noteration").mkdir()
    
    yield tmp_dir
    
    shutil.rmtree(tmp_dir)

from dataclasses import dataclass
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "static" / "samples"


@dataclass(frozen=True)
class Sample:
    id: str
    label: str

    @property
    def filename(self) -> str:
        return f"{self.id}.jpg"


# The ids are the only names a client can send, so the list is a whitelist of files on disk.
SAMPLES = (
    Sample("cocina-living", "Cocina y living"),
    Sample("monoambiente", "Monoambiente"),
    Sample("living-comedor", "Living comedor"),
    Sample("cocina-desayunador", "Cocina con desayunador"),
    Sample("comedor", "Comedor"),
    Sample("living", "Living"),
)
_SAMPLES_BY_ID = {sample.id: sample for sample in SAMPLES}


def read_sample(sample_id: str) -> bytes | None:
    """Return the bytes of a sample photo, or None when the id is not in the whitelist.

    The path is built from the whitelisted filename, never from the received text.
    """
    sample = _SAMPLES_BY_ID.get(sample_id)
    if sample is None:
        return None
    return (SAMPLES_DIR / sample.filename).read_bytes()

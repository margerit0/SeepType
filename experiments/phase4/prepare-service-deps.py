"""Extract additional Boost source files from the existing fixed archive only."""
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache"
marker = CACHE / "src/boost_1_84_0/.study-service-sources"
if not marker.exists():
    prefixes = tuple(f"boost_1_84_0/libs/{name}/src/" for name in ["serialization", "thread", "chrono"])
    with tarfile.open(CACHE / "downloads/boost_1_84_0.tar.bz2", "r|bz2") as archive:
        for member in archive:
            if (member.name.startswith(prefixes) or member.name == "boost_1_84_0/LICENSE_1_0.txt") and (member.isfile() or member.isdir()):
                archive.extract(member, CACHE / "src", filter="data")
    marker.write_text("Boost 1.84.0; archive already fixed by phase3/dependencies.lock.json\n", encoding="ascii")
print("Boost serialization, thread and chrono sources ready; no installation or download.")

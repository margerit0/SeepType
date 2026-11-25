"""Restore only fixed, hash-verified Android native source inputs."""
from __future__ import annotations

import concurrent.futures
import difflib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, DOWNLOADS, ROOT, digest, extract, fetch, json_write, write


def prepare():
    lock = json.loads((ROOT / "licensing/product-sources.lock.json").read_text())
    receipts = []

    def restore(item):
        archive = DOWNLOADS / item["url"].split("/")[-1]
        archive = archive.with_name(item["id"] + "-" + archive.name + ".tar.gz")
        expected = item.get("upstream_archive_sha256", item["archive_sha256"])
        fetch(item["url"], archive, expected)
        destination = CACHE / "src" / {"librime-lua": "librime/plugins/lua", "lua-thirdparty": "librime/plugins/lua/thirdparty"}.get(item["id"], item["id"])
        if not (destination / ".study-source.json").exists():
            if item["id"] == "lua-thirdparty":
                select = lambda name: name.startswith("lua5.4/")
            elif item["id"] == "librime":
                select = lambda name: not name.startswith("data/")
            elif item["id"] == "rime-luna-pinyin":
                select = lambda name: name in item["files"]
            else:
                select = lambda _: True
            extract(archive, destination, select)
            for name, expected_file in item.get("files", {}).items():
                if digest(destination / name) != expected_file:
                    raise ValueError("Selected source mismatch: " + name)
            json_write(destination / ".study-source.json", {"id": item["id"], "commit": item["commit"], "sha256": expected})
        return {"id": item["id"], "commit": item["commit"], "url": item["url"], "sha256": expected}

    # librime and its plugins share a destination; restore those sequentially.
    nested = {"librime", "librime-lua", "lua-thirdparty"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        tasks = [executor.submit(restore, item) for item in lock["sources"] if item["id"] not in nested]
        for item in lock["sources"]:
            if item["id"] in nested:
                receipts.append(restore(item))
        receipts.extend(task.result() for task in tasks)

    boost_url = "https://archives.boost.io/release/1.84.0/source/boost_1_84_0.tar.bz2"
    boost_sha = "cc4b893acf645c9d4b698e9a0f08ca8846aa5d6c68275c14c3e7949c24109454"
    boost = CACHE / "src/boost"
    if not (boost / "boost/version.hpp").exists():
        archive = fetch(boost_url, DOWNLOADS / "boost_1_84_0.tar.bz2", boost_sha)
        extract(archive, boost, lambda name: name.startswith("boost/") or name == "LICENSE_1_0.txt")
        archive.unlink()
    receipts.append({"id": "boost-headers", "version": "1.84.0", "url": boost_url, "sha256": boost_sha})

    patch_sources()
    json_write(CACHE / "native-sources.json", receipts)
    print(f"Prepared {len(receipts)} pinned native source inputs.")


def patch_sources():
    replacements = {}

    def replace(name, before, after):
        replacements.setdefault(name, []).append((before, after))

    replace("librime/src/rime/gear/memory.cc", "void Memory::OnCommit(Context* ctx) {\n",
            "void Memory::OnCommit(Context* ctx) {\n"
            '  // StudyIME: pause new learning without dropping existing scores.\n'
            '  if (ctx->get_property("study_user_learning") == "0")\n'
            '    return;\n')
    replace("librime/src/rime/gear/memory.cc",
            "  CommitEntry commit_entry(this);\n",
            "  CommitEntry commit_entry(this);\n"
            "  vector<an<Phrase>> selected_phrases;\n")
    replace("librime/src/rime/gear/memory.cc",
            "      commit_entry.AppendPhrase(phrase);\n"
            "    }\n"
            "    if (!recognized || seg.status >= Segment::kConfirmed) {\n"
            "      commit_entry.Save();\n",
            "      commit_entry.AppendPhrase(phrase);\n"
            "      if (seg.status >= Segment::kSelected && phrase->code().size() > 1)\n"
            "        selected_phrases.push_back(phrase);\n"
            "    }\n"
            "    if (!recognized || seg.status >= Segment::kConfirmed) {\n"
            "      commit_entry.Save();\n"
            "      // A selected sentence can be flattened into individual words by\n"
            "      // AppendPhrase. Learn the selected span as a phrase as well.\n"
            "      for (const auto& selected : selected_phrases) {\n"
            "        if (selected->code().size() == commit_entry.code.size())\n"
            "          continue;\n"
            "        CommitEntry selection(this);\n"
            "        selection.AppendPhrase(selected);\n"
            "        selection.Save();\n"
            "      }\n"
            "      selected_phrases.clear();\n")
    replace("librime/CMakeLists.txt", "  add_subdirectory(tools)\n", "  # StudyIME Android uses the C API, not standalone tools.\n")
    replace("opencc/CMakeLists.txt", '  find_library(LIBMARISA NAMES marisa)',
            '  find_package(marisa CONFIG REQUIRED)\n  set(LIBMARISA marisa)')
    replace("opencc/CMakeLists.txt", '  -DPKGDATADIR="${DIR_SHARE_OPENCC}"\n',
            '  # StudyIME: no build-machine fallback data path.\n')
    replace("opencc/CMakeLists.txt", 'add_subdirectory(data)\n', '# StudyIME: no conversion data used by the simplified source dictionary.\n')
    replace("opencc/src/CMakeLists.txt", 'add_subdirectory(tools)\n', '# StudyIME: OpenCC library only.\n')
    patches = []
    for name, edits in replacements.items():
        path = CACHE / "src" / name
        original = path.read_text(encoding="utf-8")
        # Reconstruct the full patch even when earlier edits are already cached.
        for before, after in reversed(edits):
            if after in original:
                original = original.replace(after, before, 1)
        updated = original
        for before, after in edits:
            if updated.count(before) != 1:
                raise ValueError("Upstream patch context changed: " + name)
            updated = updated.replace(before, after, 1)
        patches.extend(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                           fromfile="a/" + name, tofile="b/" + name))
        write(path, updated)
    write(ROOT / "android/native/patches/rime-android.patch", "".join(patches))


if __name__ == "__main__":
    prepare()

"""Pinned downloads and extraction only. Does NOT run any installer or register IMEs."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile
import urllib.request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CACHE=ROOT/".cache"
DOWNLOADS=CACHE/"downloads"
DOWNLOADS.mkdir(parents=True,exist_ok=True)
lock=json.loads((HERE/"dependencies.lock.json").read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def run(*args):
    subprocess.run([str(a) for a in args],cwd=ROOT,check=True)


for artifact in lock["artifacts"]:
    target=DOWNLOADS/artifact["name"]
    if not target.exists():
        part=target.with_suffix(target.suffix+".part")
        request=urllib.request.Request(artifact["url"],headers={"User-Agent":"ime-isolated-spike"})
        with urllib.request.urlopen(request,timeout=60) as source, part.open("wb") as output:
            while chunk:=source.read(1024*1024): output.write(chunk)
        if digest(part)!=artifact["sha256"]: raise RuntimeError("SHA256 mismatch: "+part.name)
        part.replace(target)
    if digest(target)!=artifact["sha256"]: raise RuntimeError("SHA256 mismatch: "+target.name)

seven=CACHE/"tools/7zip/7z.exe"
if not seven.exists():
    run(DOWNLOADS/"7zr.exe","x",DOWNLOADS/"7z2605-x64.exe",f"-o{seven.parent}","-y")
if not (CACHE/"weasel-0.17.4/rime.dll").exists():
    run(seven,"x",DOWNLOADS/"weasel-0.17.4.0-installer.exe",f"-o{CACHE/'weasel-0.17.4'}","-y")
if not (CACHE/"rime-1.13.1/dist/include/rime_api.h").exists():
    run(seven,"x",DOWNLOADS/"rime-1c23358-Windows-msvc-x64.7z",f"-o{CACHE/'rime-1.13.1'}","-y")
if digest(ROOT/lock["runtime_dll"]["path"])!=lock["runtime_dll"]["sha256"]:
    raise RuntimeError("Unexpected bundled runtime DLL")
source=lock["weasel_source"]
checkout=CACHE/"src/weasel"
if not checkout.exists():
    checkout.parent.mkdir(parents=True,exist_ok=True)
    run("git","clone","--depth","1","--branch",source["tag"],source["repository"],checkout)
head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=checkout,text=True).strip()
if head!=source["commit"]: raise RuntimeError("Unexpected Weasel checkout revision")
marker=CACHE/"src/boost_1_84_0/.study-headers-complete"
if not marker.exists():
    with tarfile.open(DOWNLOADS/"boost_1_84_0.tar.bz2","r|bz2") as archive:
        for member in archive:
            if member.name.startswith("boost_1_84_0/boost/") and (member.isfile() or member.isdir()):
                archive.extract(member,CACHE/"src",filter="data")
    marker.write_text(lock["artifacts"][-1]["sha256"],encoding="ascii")
print("Pinned dependencies ready; no installer was run.")

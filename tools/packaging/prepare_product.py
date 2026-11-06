"""Derive a separate installable-product overlay from the tested v0.5 overlay."""
from pathlib import Path
import difflib
import io
import json
import re
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, package_path, product, write_changed
from tools.packaging.identity import generate, guid


def prepare():
    data = product()
    generated = generate()
    base = CACHE / "base-weasel"
    upstream = ROOT / ".cache/src/weasel"
    output = CACHE / "weasel"
    pin = json.loads((ROOT / "experiments/phase3/dependencies.lock.json").read_text())["weasel_source"]["commit"]
    # Read the committed tree, never the mutable developer checkout. The full
    # product tree also replaces obsolete headers left by earlier experiments.
    committed = {}
    archive = subprocess.check_output(["git", "archive", "--format=tar", pin], cwd=upstream)
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        for member in bundle:
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Unexpected Weasel source archive member: " + member.name)
            package_path(member.name)
            committed[member.name] = bundle.extractfile(member).read()
    subprocess.run([sys.executable, str(ROOT / "experiments/phase4/prepare-weasel.py"),
                    "--output", str(base), "--patch-output", str(CACHE / "base-weasel.patch")],
                   cwd=ROOT, check=True)
    base_files = set(json.loads((base / "overlay-files.json").read_text(encoding="utf-8")))
    files, originals = {}, {}

    def source(relative):
        if relative not in files:
            raw = (base / relative).read_bytes() if relative in base_files else committed[relative]
            text = raw.decode("utf-16" if raw.startswith(b"\xff\xfe") else "utf-8-sig").replace("\r\n", "\n")
            files[relative] = originals[relative] = text
        return files[relative]

    def replace(relative, before, after, count=1):
        value = source(relative)
        if value.count(before) != count:
            raise ValueError(f"Product overlay context changed: {relative}: {before[:70]!r}")
        files[relative] = value.replace(before, after)

    for relative in sorted(base_files):
        source(relative)
    relative = "include/WeaselIPC.h"
    replace(relative, "#include <stdexcept>", '#include <stdexcept>\n#include <study/windows/ProductRuntime.h>')
    a = source(relative).index("inline std::wstring GetPipeName() {")
    b = source(relative).index("\n}", a) + 2
    replace(relative, source(relative)[a:b], 'inline std::wstring GetPipeName() { return study::ProductPipeName(); }')
    replace(relative, 'L"StudyImePhase4IPCWindow"', 'L"StudyIME.IPC.v1"')
    constants = "include/WeaselConstants.h"
    source(constants)
    files[constants] = '''#pragma once
#include <ProductIdentity.h>
#define WEASEL_CODE_NAME "StudyIME"
#define WEASEL_REG_KEY study::kProductRegistryKey
#define RIME_REG_KEY study::kProductRegistryKey
#define WEASEL_VERSION study::kProductVersion
'''
    utility = "include/WeaselUtility.h"
    replace(utility, "inline fs::path WeaselLogPath() {", '#include <study/windows/ProductRuntime.h>\n#include <ProductIdentity.h>\ninline fs::path WeaselLogPath() {')
    a = source(utility).index("inline fs::path WeaselLogPath() {")
    b = source(utility).index("\n}", a) + 2
    replace(utility, source(utility)[a:b], '''inline fs::path WeaselLogPath() {
  const auto logs = study::ProductUserRoot() / L"rime/logs";
  fs::create_directories(logs);
  return logs;
}''')
    a = source(utility).index("inline std::wstring get_weasel_ime_name() {")
    b = source(utility).index("\n}", a) + 2
    replace(utility, source(utility)[a:b], 'inline std::wstring get_weasel_ime_name() { return study::kProductName; }')
    replace(utility, 'L"Software\\\\Rime\\\\Weasel"', 'study::kProductRegistryKey')
    t = "WeaselTSF/WeaselTSF.cpp"
    replace(t, '#ifndef WEASEL_STUDY_ISOLATED\n  if (!_InitKeyEventSink())\n    goto ExitError;\n#endif', '  if (!_InitKeyEventSink())\n    goto ExitError;')
    replace(t, '#ifndef WEASEL_STUDY_ISOLATED\n  _UninitKeyEventSink();\n#endif', '  _UninitKeyEventSink();')
    a = source(t).index("#ifndef WEASEL_STUDY_ISOLATED")
    b = source(t).index("#endif", a) + len("#endif")
    replace(t, source(t)[a:b], '''  // The installed TIP owns only its own compartment and key sink.
  // Upstream tray/menu, updater and global preserved shortcuts are not enabled.
  if (!_IsKeyboardOpen()) _SetKeyboardOpen(TRUE);
  if (!_InitCompartment()) goto ExitError;''')
    replace(t, 'L"Software\\\\Rime\\\\weasel"', 'study::kProductRegistryKey')
    replace(t, '  if (m_client.Echo()) return true;\n  _Reconnect();', '  if (m_client.Echo()) return true;\n  if (!study::EnsureProductService()) return false;\n  _Reconnect();')
    globals_path = "WeaselTSF/Globals.cpp"
    replace(globals_path, '#include "Globals.h"', '#include "Globals.h"\n#include <ProductIdentity.h>')
    global_names = {
        'c_clsidTextService': 'text_service', 'c_guidProfile': 'language_profile',
        'c_guidLangBarItemButton': 'language_bar', 'c_guidDisplayAttributeInput': 'display_attribute',
        'GUID_LBI_INPUTMODE': 'input_mode', 'GUID_IME_MODE_PRESERVED_KEY': 'preserved_key',
    }
    for name, key in global_names.items():
        pattern = r'(?:static )?const GUID ' + name + r' = \{.*?\};'
        matched = re.search(pattern, source(globals_path), re.S)
        if not matched: raise ValueError('Missing product GUID ' + name)
        replace(globals_path, matched[0], f'const GUID {name} = {guid(data["guids"][key])};')
    server = "WeaselTSF/Server.cpp"
    replace(server, '#include "Register.h"', '#include <study/windows/ProductRegistration.h>\n#include <ProductIdentity.h>')
    a = source(server).index('STDAPI DllRegisterServer()')
    files[server] = source(server)[:a] + '''STDAPI DllRegisterServer() { return study::RegisterProductModule(g_hInst); }
STDAPI DllUnregisterServer() { return study::UnregisterProductModule(g_hInst); }
extern "C" const char* WINAPI StudyProductIdentity() { return study::kProductIdentityJson; }
'''
    replace(server, '\n  if (g_classFactory == NULL) {', '\n  if (!ppvObject) return E_INVALIDARG;\n  *ppvObject = nullptr;\n  if (!IsEqualCLSID(rclsid, study::kTextServiceGuid)) return CLASS_E_CLASSNOTAVAILABLE;\n  if (g_classFactory == NULL) {')
    rime = "RimeWithWeasel/RimeWithWeasel.cpp"
    replace(rime, '"rime.weasel"', '"rime.studyime"', count=2)
    replace(rime, '"rime.study-service-test"', '"rime.studyime"')
    replace(rime, '  rime_api->initialize(NULL);', '  rime_api->initialize(NULL);\n  if (rime_api->start_maintenance(False)) rime_api->join_maintenance_thread();')
    security = "WeaselIPCServer/SecurityAttribute.cpp"
    source(security)
    files[security] = '''#include "stdafx.h"
#include "SecurityAttribute.h"
#include <study/windows/ProductRuntime.h>
#include <sddl.h>
#include <stdexcept>
namespace weasel {
void SecurityAttribute::_Init() {
  const auto descriptor = L"D:P(A;;GA;;;SY)(A;;GA;;;" + study::ProductUserSid() + L")S:(ML;;NW;;;LW)";
  if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(descriptor.c_str(), SDDL_REVISION_1, &pd, nullptr))
    throw std::runtime_error("Cannot create the StudyIME pipe security descriptor");
  sa.nLength = sizeof(sa); sa.lpSecurityDescriptor = pd; sa.bInheritHandle = FALSE;
}
SECURITY_ATTRIBUTES* SecurityAttribute::get_attr() { return &sa; }
}
'''
    pipe = "WeaselIPC/PipeChannel.cpp"
    replace(pipe, '#include <PipeChannel.h>', '#include <PipeChannel.h>\n#include <study/windows/ProductRuntime.h>')
    replace(pipe, '    // connected to the pipe\n    return pipe;', '''    if (!study::ProductPipeServerMatchesUser(pipe)) {
      CloseHandle(pipe);
      throw static_cast<DWORD>(ERROR_ACCESS_DENIED);
    }
    return pipe;''')
    replace(pipe, "PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,", "PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,")
    replace(pipe, '  while (_Invalid(pipe = _TryConnect()))\n    ::WaitNamedPipe(name, 500);', '''  const auto deadline = GetTickCount64() + 500;
  while (_Invalid(pipe = _TryConnect())) {
    if (GetTickCount64() >= deadline) throw static_cast<DWORD>(ERROR_TIMEOUT);
    ::WaitNamedPipe(name, 50);
  }''')
    patches = []
    for relative, value in sorted(files.items()):
        committed[relative] = value.encode("utf-8")
        if relative in originals:
            patches.extend(difflib.unified_diff(originals[relative].splitlines(True), value.splitlines(True), fromfile="a/" + relative, tofile="b/" + relative))
    # This named cache directory contains generated output only. Check every
    # target before replacing/pruning it; leave the old developer trees alone.
    if output.is_symlink() or output.is_junction() or not output.resolve().is_relative_to(CACHE.resolve()):
        raise ValueError("Unsafe generated product source directory")
    for path in sorted(output.rglob("*")):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(output.resolve()):
            raise ValueError("Reparse point in generated product source directory")
        if path.is_file() and path.relative_to(output).as_posix() not in committed:
            path.unlink()
    for relative, content in sorted(committed.items()):
        write_changed(output / relative, content)
    write_changed(ROOT / "packaging/patches/weasel-product.patch", "".join(patches))
    print(f"Prepared StudyIME {data['version']} product overlay; no registration or installation.")


if __name__ == "__main__":
    prepare()

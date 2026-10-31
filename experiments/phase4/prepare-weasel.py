"""Generate a reviewable patch and overlay from the already pinned Weasel source.

Does not change the original checkout, installed Weasel, the registry or PATH.
The isolated build fails closed unless its unique test pipe name is supplied.
"""
from pathlib import Path
import difflib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / ".cache/src/weasel"
OVERLAY = ROOT / ".cache/study-weasel"
PIN = json.loads((ROOT / "experiments/phase3/dependencies.lock.json").read_text())["weasel_source"]["commit"]
originals = {}
files = {}


def source(path):
    if path not in files:
        data = subprocess.check_output(["git", "show", f"{PIN}:{path}"], cwd=UPSTREAM).decode("utf-8-sig")
        originals[path] = files[path] = data.replace("\r\n", "\n")
    return files[path]


def replace(path, before, after, count=1):
    data = source(path)
    if data.count(before) != count:
        raise RuntimeError(f"Patch context changed in {path}: {before[:70]!r}")
    files[path] = data.replace(before, after)


def write_changed(path, content):
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


ipc = "include/WeaselIPC.h"
replace(ipc, "#include <KeyEvent.h>", "#include <KeyEvent.h>\n#include <study/StudyProtocol.h>\n#include <stdexcept>")
replace(ipc, '#define WEASEL_IPC_WINDOW L"WeaselIPCWindow_1.0"', '''#ifdef WEASEL_STUDY_ISOLATED
#define WEASEL_IPC_WINDOW L"StudyImePhase4IPCWindow"
#else
#define WEASEL_IPC_WINDOW L"WeaselIPCWindow_1.0"
#endif''')
replace(ipc, "  WEASEL_IPC_LAST_COMMAND", "  WEASEL_IPC_STUDY_ACTION,\n  WEASEL_IPC_LAST_COMMAND")
replace(ipc, "  virtual void FocusIn(DWORD param, DWORD session_id) {}", '''  virtual bool StudyAction(const wchar_t* request, DWORD session_id, EatLine eat) {
    return false;
  }
  virtual void FocusIn(DWORD param, DWORD session_id) {}''')
replace(ipc, "  bool ChangePage(bool backward);", "  bool ChangePage(bool backward);\n  bool StudyAction(const study::ActionRequest& request);")
replace(ipc, "inline std::wstring GetPipeName() {", '''inline std::wstring GetPipeName() {
#ifdef WEASEL_STUDY_ISOLATED
  wchar_t name[96]{};
  const DWORD length = GetEnvironmentVariableW(L"STUDY_IPC_TEST_NAME", name, 96);
  if (length < 16 || length >= 96)
    throw std::runtime_error("Missing isolated study pipe name");
  for (DWORD i = 0; i < length; ++i)
    if (!((name[i] >= L'a' && name[i] <= L'z') ||
          (name[i] >= L'0' && name[i] <= L'9') || name[i] == L'-'))
      throw std::runtime_error("Invalid isolated study pipe name");
  return std::wstring(L"\\\\\\\\.\\\\pipe\\\\StudyIme-Phase4-") + name;
#else''')
replace(ipc, "  return pipe_name;\n}", "  return pipe_name;\n#endif\n}")

clienth = "WeaselIPC/WeaselClientImpl.h"
replace(clienth, "  bool ChangePage(bool backward);", "  bool ChangePage(bool backward);\n  bool StudyAction(const study::ActionRequest& request);")
client = "WeaselIPC/WeaselClientImpl.cpp"
replace(client, "void ClientImpl::UpdateInputPosition(RECT const& rc) {", '''bool ClientImpl::StudyAction(const study::ActionRequest& request) {
  if (!_Active()) return false;
  const auto wire = study::EncodeRequest(request);
  study::ActionRequest checked;
  if (!study::DecodeRequest(wire, checked)) return false;
  channel << wire;
  return _SendMessage(WEASEL_IPC_STUDY_ACTION, 0, session_id) != 0;
}

void ClientImpl::UpdateInputPosition(RECT const& rc) {''')
replace(client, "void Client::UpdateInputPosition(RECT const& rc) {", '''bool Client::StudyAction(const study::ActionRequest& request) {
  return m_pImpl->StudyAction(request);
}

void Client::UpdateInputPosition(RECT const& rc) {''')

rh = "include/RimeWithWeasel.h"
replace(rh, "#include <rime_api.h>", "#include <rime_api.h>\n#include <study/StudyService.h>")
replace(rh, "  virtual void FocusIn(DWORD param, WeaselSessionId ipc_id);", '''  virtual bool StudyAction(const wchar_t* request, WeaselSessionId ipc_id, EatLine eat);
  virtual void FocusIn(DWORD param, WeaselSessionId ipc_id);''')
replace(rh, "  bool _Respond(WeaselSessionId ipc_id, EatLine eat);", "  bool _Respond(WeaselSessionId ipc_id, EatLine eat, bool consume_commit = true);")
replace(rh, "  SessionStatusMap m_session_status_map;", "  SessionStatusMap m_session_status_map;\n  study::StudyService m_study;")

rime = "RimeWithWeasel/RimeWithWeasel.cpp"
replace(rime, "void RimeWithWeaselHandler::Finalize() {", "void RimeWithWeaselHandler::Finalize() {\n  m_study.Clear();")
replace(rime, "  m_ui->style() = session_status.style;\n  // show session's", "  m_study.Attach(ipc_id, rime_api, session_id);\n  m_ui->style() = session_status.style;\n  // show session's")
replace(rime, "DWORD RimeWithWeaselHandler::RemoveSession(WeaselSessionId ipc_id) {", "DWORD RimeWithWeaselHandler::RemoveSession(WeaselSessionId ipc_id) {\n  m_study.Remove(ipc_id);")
replace(rime, "  Bool handled = rime_api->process_key(session_id, keyEvent.keycode,", "  m_study.Activate(ipc_id);\n  m_study.Invalidate(ipc_id);\n  Bool handled = rime_api->process_key(session_id, keyEvent.keycode,")
for call in ["commit_composition(to_session_id(ipc_id))", "clear_composition(to_session_id(ipc_id))", "select_candidate_on_current_page(to_session_id(ipc_id), index)"]:
    replace(rime, f"  rime_api->{call};", f"  m_study.Invalidate(ipc_id);\n  rime_api->{call};")
replace(rime, "  bool res = rime_api->highlight_candidate_on_current_page(", "  m_study.Invalidate(ipc_id);\n  bool res = rime_api->highlight_candidate_on_current_page(")
replace(rime, "  bool res = rime_api->change_page(to_session_id(ipc_id), backward);", "  m_study.Invalidate(ipc_id);\n  bool res = rime_api->change_page(to_session_id(ipc_id), backward);")
replace(rime, "void RimeWithWeaselHandler::FocusIn(DWORD client_caps, WeaselSessionId ipc_id) {", '''bool RimeWithWeaselHandler::StudyAction(const wchar_t* wire,
                                      WeaselSessionId ipc_id, EatLine eat) {
  if (m_disabled || !wire || !eat || !m_session_status_map.count(ipc_id))
    return false;
  const size_t length = wcsnlen(wire, study::kMaxRequestChars + 1);
  study::ActionRequest request;
  if (!study::DecodeRequest(std::wstring_view(wire, length), request))
    return false;
  const bool applied = m_study.Apply(ipc_id, request);
  // Inspection and rejected requests must not drain application commits.
  _Respond(ipc_id, eat, applied && request.action == study::Action::CommitEnglish);
  _UpdateUI(ipc_id);
  return applied;
}

void RimeWithWeaselHandler::FocusIn(DWORD client_caps, WeaselSessionId ipc_id) {
  m_study.Activate(ipc_id);''')
replace(rime, "void RimeWithWeaselHandler::FocusOut(DWORD param, WeaselSessionId ipc_id) {", "void RimeWithWeaselHandler::FocusOut(DWORD param, WeaselSessionId ipc_id) {\n  m_study.FocusOut(ipc_id);")
replace(rime, "  if (m_active_session != ipc_id) {\n    _UpdateUI(ipc_id);", "  if (m_active_session != ipc_id) {\n    m_study.Activate(ipc_id);\n    _UpdateUI(ipc_id);")
replace(rime, "  // from no-session client, not actual typing session", "  for (const auto& item : m_session_status_map) m_study.Invalidate(item.first);\n  // from no-session client, not actual typing session")
replace(rime, '        if (pair.first != ipc_id)\n          rime_api->set_option(to_session_id(pair.first), "ascii_mode",\n                               !!status.is_ascii_mode);', '        if (pair.first != ipc_id) {\n          m_study.Invalidate(pair.first);\n          rime_api->set_option(to_session_id(pair.first), "ascii_mode",\n                               !!status.is_ascii_mode);\n        }')
replace(rime, "  m_session_status_map.clear();\n}", "  m_study.Clear();\n  m_session_status_map.clear();\n}")
replace(rime, "bool RimeWithWeaselHandler::_Respond(WeaselSessionId ipc_id, EatLine eat) {", "bool RimeWithWeaselHandler::_Respond(WeaselSessionId ipc_id, EatLine eat, bool consume_commit) {")
replace(rime, "  if (rime_api->get_commit(session_id, &commit)) {", "  if (consume_commit && rime_api->get_commit(session_id, &commit)) {")
replace(rime, "  // configuration information\n", '''  const auto study_state = m_study.State(ipc_id);
  if (study_state.stamp.service) {
    actions.insert("study");
    messages.push_back(study::EncodeState(study_state));
  }

  // configuration information
''')
replace(rime, "  weasel_traits.app_name = \"rime.weasel\";", '''  weasel_traits.app_name = "rime.weasel";
#ifdef WEASEL_STUDY_ISOLATED
  weasel_traits.app_name = "rime.study-service-test";
  weasel_traits.min_log_level = 2;
  const char* modules[] = {"default", "lua", nullptr};
  weasel_traits.modules = modules;
#endif''')
replace(rime, "bool RimeWithWeaselHandler::_IsDeployerRunning() {", "bool RimeWithWeaselHandler::_IsDeployerRunning() {\n#ifdef WEASEL_STUDY_ISOLATED\n  return false;\n#endif")

utility = "include/WeaselUtility.h"
replace(utility, "inline fs::path WeaselLogPath() {", "inline fs::path WeaselLogPath() {\n#ifdef WEASEL_STUDY_ISOLATED\n  const auto logs = WeaselUserDataPath() / L\"logs\";\n  fs::create_directories(logs);\n  return logs;\n#else")
replace(utility, "  return path;\n}", "  return path;\n#endif\n}")

sh = "WeaselIPCServer/WeaselServerImpl.h"
replace(sh, "  DWORD OnChangePage(WEASEL_IPC_COMMAND uMsg, DWORD wParam, DWORD lParam);", "  DWORD OnChangePage(WEASEL_IPC_COMMAND uMsg, DWORD wParam, DWORD lParam);\n  DWORD OnStudyAction(WEASEL_IPC_COMMAND uMsg, DWORD wParam, DWORD lParam);")
replace(sh, "  std::unique_ptr<PipeServer> channel;", "  std::unique_ptr<PipeServer> channel;\n  PipeServer* requestChannel = nullptr;  // only while the handler mutex is held")
server = "WeaselIPCServer/WeaselServerImpl.cpp"
replace(server, "using ServerHandler = std::function<void(PipeMessage, Respond)>;", "using ServerHandler = std::function<void(PipeMessage, PipeServer&, Respond)>;")
replace(server, "static std::mutex g_api_mutex;", "")
replace(server, "using namespace weasel;", "using namespace weasel;\n\nstatic std::recursive_mutex g_api_mutex;")
replace(server, '  std::wstring instanceName = L"(WEASEL)Furandōru-Sukāretto-";', '''#ifdef WEASEL_STUDY_ISOLATED
  std::wstring instanceName = GetPipeName() + L"-instance";
  std::replace(instanceName.begin(), instanceName.end(), L'\\\\', L'-');
#else
  std::wstring instanceName = L"(WEASEL)Furandōru-Sukāretto-";
#endif''')
replace(server, "  auto listener = [this](PipeMessage msg, PipeServer::Respond resp) -> void {\n    std::lock_guard guard(g_api_mutex);\n    HandlePipeMessage(msg, resp);\n  };", '''  auto listener = [this](PipeMessage msg, PipeServer& connection,
                         PipeServer::Respond resp) -> void {
    std::lock_guard guard(g_api_mutex);
    requestChannel = &connection;
    try { HandlePipeMessage(msg, resp); }
    catch (...) { requestChannel = nullptr; throw; }
    requestChannel = nullptr;
  };''')
replace(server, "reinterpret_cast<LPWSTR>(channel->ReceiveBuffer())", "reinterpret_cast<LPWSTR>(requestChannel->ReceiveBuffer())")
replace(server, "*channel << msg;", "*requestChannel << msg;", count=4)
replace(server, "#define MAP_PIPE_MSG_HANDLE", '''DWORD ServerImpl::OnStudyAction(WEASEL_IPC_COMMAND, DWORD, DWORD session) {
  if (!m_pRequestHandler || !requestChannel) return 0;
  return m_pRequestHandler->StudyAction(
      reinterpret_cast<const wchar_t*>(requestChannel->ReceiveBuffer()), session,
      [this](std::wstring& message) { *requestChannel << message; return true; });
}

#define MAP_PIPE_MSG_HANDLE''')
replace(server, "  PIPE_MSG_HANDLE(WEASEL_IPC_TRAY_COMMAND, OnCommand);", "  PIPE_MSG_HANDLE(WEASEL_IPC_TRAY_COMMAND, OnCommand);\n  PIPE_MSG_HANDLE(WEASEL_IPC_STUDY_ACTION, OnStudyAction);")
replace(server, "  try {\n    for (;;) {\n      Res msg;\n      _Receive(pipe, &msg, sizeof(msg));\n      handler(msg, [this, pipe](Msg resp) { _Send(pipe, resp); });", "  PipeServer connection(std::wstring(), nullptr);\n  try {\n    for (;;) {\n      Res msg;\n      connection._Receive(pipe, &msg, sizeof(msg));\n      handler(msg, connection, [&connection, pipe](Msg resp) { connection._Send(pipe, resp); });")
# Serialize UI-originating options with pipe-originating Rime operations too.
for signature in [
    "LRESULT ServerImpl::OnColorChange(UINT uMsg,\n                                  WPARAM wParam,\n                                  LPARAM lParam,\n                                  BOOL& bHandled) {",
    "LRESULT ServerImpl::OnCommand(UINT uMsg,\n                              WPARAM wParam,\n                              LPARAM lParam,\n                              BOOL& bHandled) {",
    "LRESULT ServerImpl::OnEndSystemSession(UINT uMsg,\n                                       WPARAM wParam,\n                                       LPARAM lParam,\n                                       BOOL& bHandled) {",
]:
    replace(server, signature, signature + "\n  std::lock_guard guard(g_api_mutex);")

replace("include/PipeChannel.h", "  char* ReceiveBuffer() const { return buffer.get() + _ResSize; }", "  // _Receive stores the body at offset zero after reading the header.\n  char* ReceiveBuffer() const { return buffer.get(); }")
pipe = "WeaselIPC/PipeChannel.cpp"
replace(pipe, "  DWORD lread;\n  BOOL success = ::ReadFile(pipe, msg, rec_len, &lread, NULL);", "  memset(buffer.get(), 0, buff_size);\n  DWORD lread = 0;\n  BOOL success = ::ReadFile(pipe, msg, rec_len, &lread, NULL);\n  if (lread != rec_len) throw static_cast<DWORD>(ERROR_INVALID_DATA);")
replace(pipe, "  if (pipe == INVALID_HANDLE_VALUE || !::ConnectNamedPipe(pipe, NULL)) {\n    _ThrowLastError;\n  }", "  if (pipe == INVALID_HANDLE_VALUE) { _ThrowLastError; }\n  if (!::ConnectNamedPipe(pipe, NULL) && GetLastError() != ERROR_PIPE_CONNECTED) {\n    const DWORD error = GetLastError();\n    CloseHandle(pipe);\n    throw error;\n  }")

patch = []
for path, content in files.items():
    target = OVERLAY / path
    write_changed(target, content)
    patch.extend(difflib.unified_diff(originals[path].splitlines(True), content.splitlines(True), fromfile="a/" + path, tofile="b/" + path))
for directory in ["RimeWithWeasel", "WeaselIPC", "WeaselIPCServer"]:
    for name in ["stdafx.h", "targetver.h"]:
        path = f"{directory}/{name}"
        write_changed(OVERLAY / path, source(path))
patch_path = ROOT / "experiments/phase4/patches/weasel-study-ipc.patch"
patch_path.parent.mkdir(parents=True, exist_ok=True)
write_changed(patch_path, "".join(patch))
print(f"Prepared {len(files)} files from Weasel {PIN[:12]}; original checkout retained.")

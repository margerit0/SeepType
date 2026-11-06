#include "ProductRuntime.h"
#include <ProductIdentity.h>
#include <sddl.h>
#include <shlobj.h>
#include <atomic>
#include <stdexcept>
#include <vector>

namespace study {
namespace {
std::wstring Environment(const wchar_t* name) {
  const DWORD size = GetEnvironmentVariableW(name, nullptr, 0);
  if (!size) return {};
  if (size > 32768) throw std::runtime_error("StudyIME environment value is too long");
  std::vector<wchar_t> value(size);
  const DWORD read = GetEnvironmentVariableW(name, value.data(), size);
  if (!read || read >= size) throw std::runtime_error("StudyIME environment value changed");
  return {value.data(), read};
}
}
std::filesystem::path ProductRoot() {
  HMODULE module = nullptr;
  if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
          GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
          reinterpret_cast<LPCWSTR>(&ProductRoot), &module))
    throw std::runtime_error("Cannot locate the StudyIME module");
  wchar_t file[32768]{};
  const DWORD length = GetModuleFileNameW(module, file, 32768);
  if (!length || length >= 32768) throw std::runtime_error("Invalid StudyIME module path");
  auto root = std::filesystem::path(file).parent_path().parent_path();
  if (!std::filesystem::is_regular_file(root / L"product.json"))
    throw std::runtime_error("Incomplete StudyIME package: product.json is missing");
  return root;
}
std::filesystem::path ProductUserRoot() {
  // Explicit opt-in for the relocation probe. Normal installed clients use the
  // Windows known folder and never inspect an installed Weasel configuration.
  const auto override = Environment(L"STUDYIME_DEV_DATA_ROOT");
  if (!override.empty()) {
    std::filesystem::path path(override);
    if (!path.is_absolute()) throw std::runtime_error("Developer data root must be absolute");
    return path.lexically_normal();
  }
  PWSTR local = nullptr;
  if (FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local)))
    throw std::runtime_error("Cannot locate LocalAppData");
  auto path = std::filesystem::path(local) / kProductFolder;
  CoTaskMemFree(local);
  return path;
}
std::wstring ProductUserSid() {
  HANDLE token = nullptr;
  if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token))
    throw std::runtime_error("Cannot query the StudyIME user token");
  DWORD needed = 0;
  GetTokenInformation(token, TokenUser, nullptr, 0, &needed);
  std::vector<BYTE> data(needed);
  const BOOL ok = GetTokenInformation(token, TokenUser, data.data(), needed, &needed);
  CloseHandle(token);
  if (!ok) throw std::runtime_error("Cannot query the StudyIME user SID");
  LPWSTR value = nullptr;
  if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(data.data())->User.Sid, &value))
    throw std::runtime_error("Cannot encode the StudyIME user SID");
  std::wstring result(value);
  LocalFree(value);
  return result;
}
std::wstring ProductInstanceSuffix() {
  DWORD session = 0;
  if (!ProcessIdToSessionId(GetCurrentProcessId(), &session))
    throw std::runtime_error("Cannot identify the StudyIME logon session");
  auto suffix = ProductUserSid() + L"-" + std::to_wstring(session);
  const auto development = Environment(L"STUDYIME_DEV_SESSION");
  if (!development.empty()) {
    if (development.size() < 16 || development.size() > 64 ||
        development.find_first_not_of(L"abcdefghijklmnopqrstuvwxyz0123456789-") != std::wstring::npos)
      throw std::runtime_error("Invalid StudyIME developer session");
    // A developer run must never share the normal user's mutable data.
    if (Environment(L"STUDYIME_DEV_DATA_ROOT").empty())
      throw std::runtime_error("Developer session requires a separate data root");
    suffix += L"-dev-" + development;
  } else if (!Environment(L"STUDYIME_DEV_DATA_ROOT").empty()) {
    throw std::runtime_error("Developer data root requires a separate session");
  }
  return suffix;
}
std::wstring ProductPipeName() {
  return std::wstring(L"\\\\.\\pipe\\") + kProductPipePrefix + L"-" + ProductInstanceSuffix();
}
std::wstring ProductStopEvent() {
  return L"Local\\StudyIME-Stop-" + ProductInstanceSuffix();
}
std::wstring ProductMutexName() {
  return L"Local\\StudyIME-Service-" + ProductInstanceSuffix();
}
bool ProductPipeServerMatchesUser(HANDLE pipe) {
  ULONG pid = 0;
  DWORD peerSession = 0, ownSession = 0;
  if (!GetNamedPipeServerProcessId(pipe, &pid) ||
      !ProcessIdToSessionId(pid, &peerSession) ||
      !ProcessIdToSessionId(GetCurrentProcessId(), &ownSession) || peerSession != ownSession) return false;
  HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
  if (!process) return false;
  HANDLE token = nullptr;
  const BOOL opened = OpenProcessToken(process, TOKEN_QUERY, &token);
  CloseHandle(process);
  if (!opened) return false;
  DWORD needed = 0;
  GetTokenInformation(token, TokenUser, nullptr, 0, &needed);
  std::vector<BYTE> data(needed);
  const BOOL queried = GetTokenInformation(token, TokenUser, data.data(), needed, &needed);
  CloseHandle(token);
  if (!queried) return false;
  LPWSTR peer = nullptr;
  if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(data.data())->User.Sid, &peer)) return false;
  bool same = false;
  try { same = ProductUserSid() == peer; } catch (...) {}
  LocalFree(peer);
  return same;
}
bool EnsureProductService() {
  try {
    const auto pipe = ProductPipeName();
    if (WaitNamedPipeW(pipe.c_str(), 0)) return true;
    static std::atomic<ULONGLONG> lastLaunch{0};
    const auto now = GetTickCount64();
    auto previous = lastLaunch.load(std::memory_order_relaxed);
    do {
      if (previous && (now <= previous || now - previous < 1500)) return false;
    } while (!lastLaunch.compare_exchange_weak(previous, now, std::memory_order_relaxed));
    const auto root = ProductRoot();
    const auto executable = root / L"bin/StudyIME.Service.exe";
    std::wstring command = L"\"" + executable.wstring() + L"\" --run";
    STARTUPINFOW startup{sizeof(startup)};
    startup.dwFlags = STARTF_USESHOWWINDOW;
    startup.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, FALSE,
            CREATE_NO_WINDOW, nullptr, root.c_str(), &startup, &process)) return false;
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    // Never hold an application's TSF apartment through dictionary deployment.
    // The installer prepares data before registration; subsequent keys retry.
    const auto deadline = GetTickCount64() + 800;
    do {
      if (WaitNamedPipeW(pipe.c_str(), 10)) return true;
      Sleep(10);  // WaitNamedPipe returns immediately when the first pipe is absent.
    } while (GetTickCount64() < deadline);
    return false;
  } catch (...) { return false; }
}
void PrepareProductUserData() {
  const auto user = ProductUserRoot() / L"rime";
  const auto seed = ProductRoot() / L"data/user-template";
  std::filesystem::create_directories(user);
  for (const auto& entry : std::filesystem::recursive_directory_iterator(seed)) {
    if (entry.is_symlink()) throw std::runtime_error("Unexpected link in the StudyIME data template");
    const auto target = user / entry.path().lexically_relative(seed);
    if (entry.is_directory()) std::filesystem::create_directories(target);
    else if (entry.is_regular_file())
      std::filesystem::copy_file(entry.path(), target, std::filesystem::copy_options::skip_existing);
  }
}
}

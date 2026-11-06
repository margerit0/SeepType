// Keep Rime headers in an ATL-free translation unit, matching the established
// MSVC 19.29 boundary. Paths are fixed to this repository's isolated runtime.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <RimeWithWeasel.h>
#include <filesystem>
#include <stdexcept>

static std::filesystem::path root() {
  wchar_t executable[32768]{};
  const DWORD length = GetModuleFileNameW(nullptr, executable, 32768);
  if (!length || length >= 32768) throw std::runtime_error("Cannot locate test host");
  return std::filesystem::path(executable).parent_path().parent_path().parent_path().parent_path();
}

std::filesystem::path WeaselSharedDataPath() {
  return root() / L"experiments/phase4/runtime/shared";
}
std::filesystem::path WeaselUserDataPath() {
  return root() / L"experiments/phase4/runtime/user";
}
std::string GetCustomResource(const char*, const char*) { return {}; }

extern "C" RimeApi* rime_get_api(void) {
#ifdef _WIN64
  const auto library = root() / L".cache/rime-1.13.1/dist/lib/rime.dll";
#else
  const auto library = root() / L".cache/weasel-0.17.4/rime.dll";
#endif
  static HMODULE module = LoadLibraryExW(library.c_str(),
      nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  if (!module) throw std::runtime_error("Cannot load the fixed test Rime DLL");
  const auto entry = reinterpret_cast<RimeApi*(*)()>(GetProcAddress(module, "rime_get_api"));
  if (!entry) throw std::runtime_error("Missing Rime API entry");
  return entry();
}

weasel::RequestHandler* CreateIsolatedRimeHandler(weasel::UI* ui) {
  return new RimeWithWeaselHandler(ui);
}

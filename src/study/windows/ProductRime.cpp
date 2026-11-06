// Keep Rime API headers outside the ATL translation unit, as in the v0.5 host.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <RimeWithWeasel.h>
#include "ProductRuntime.h"
#include <stdexcept>

std::filesystem::path WeaselSharedDataPath() {
  return study::ProductRoot() / L"data/shared";
}
std::filesystem::path WeaselUserDataPath() {
  return study::ProductUserRoot() / L"rime";
}
std::string GetCustomResource(const char*, const char*) { return {}; }
extern "C" RimeApi* rime_get_api(void) {
  const auto library = study::ProductRoot() / L"bin/rime.dll";
  static HMODULE module = LoadLibraryExW(library.c_str(), nullptr,
      LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (!module) throw std::runtime_error("Cannot load packaged rime.dll");
  const auto entry = reinterpret_cast<RimeApi*(*)()>(GetProcAddress(module, "rime_get_api"));
  if (!entry) throw std::runtime_error("Packaged Rime API is missing");
  return entry();
}
weasel::RequestHandler* CreateProductRimeHandler(weasel::UI* ui) {
  return new RimeWithWeaselHandler(ui);
}

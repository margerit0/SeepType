// Keep Rime API headers outside the ATL translation unit, as in the v0.5 host.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <RimeWithWeasel.h>
#include "ProductRuntime.h"
#include "ProductRime.h"
#include "UiPreferences.h"
#include <array>
#include <stdexcept>

void study::RefreshProductPreferences(void* rawApi, std::uintptr_t session,
                                     bool allowSchemaChange, bool newSession) {
  auto* api = static_cast<RimeApi*>(rawApi);
  if (!api || !session || !api->find_session(session)) return;
  const auto preferences = LoadPreferences(PreferencesPath());
  const char* input = api->get_input(session);
  if (allowSchemaChange && (!input || !*input)) {
    RIME_STRUCT(RimeStatus, status);
    if (api->get_status(session, &status)) {
      const bool change = !status.schema_id ||
          std::string(status.schema_id) != InputSchemaId(preferences.inputScheme);
      api->free_status(&status);
      if (change) {
        // Selecting a schema rebuilds the engine context. Preserve the current
        // Chinese/ASCII mode and the independent annotation switch. Never drain
        // get_commit here: that buffer still belongs to the application.
        const std::array<const char*, 4> names{
            "ascii_mode", "full_shape", "ascii_punct", "learning_mode"};
        std::array<Bool, 4> values{};
        for (size_t i = 0; i < names.size(); ++i)
          values[i] = api->get_option(session, names[i]);
        if (api->select_schema(session, InputSchemaId(preferences.inputScheme))) {
          for (size_t i = 0; i < names.size(); ++i)
            api->set_option(session, names[i], values[i]);
        }
      }
    }
  }
  if (newSession) api->set_option(session, "learning_mode", preferences.learning);
  // A property does not refresh candidates or disturb a partial selection.
  // Read at every native commit boundary, including mouse and TSF commits.
  api->set_property(session, "study_user_learning", preferences.userLearning ? "1" : "0");
}

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

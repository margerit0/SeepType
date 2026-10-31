#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <rime_api.h>
#include "StudyEngine.h"

namespace study {

struct Engine::Impl {
  HMODULE module = nullptr;
  RimeApi* api = nullptr;
  RimeSessionId session = 0;
  bool initialized = false;
  ~Impl() {
    if (session) api->destroy_session(session);
    if (initialized) api->finalize();
    if (module) FreeLibrary(module);
  }
};

Engine::Engine() : impl_(std::make_unique<Impl>()) {}
Engine::~Engine() = default;

bool Engine::Open(const std::filesystem::path& root) {
  auto& state = *impl_;
  auto dll = root / L".cache/weasel-0.17.4/rime.dll";
  state.module = LoadLibraryExW(dll.c_str(), nullptr,
      LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  if (!state.module) return false;
  auto entry = reinterpret_cast<RimeApi*(*)()>(
      GetProcAddress(state.module, "rime_get_api"));
  if (!entry) return false;
  state.api = entry();
  std::string shared = (root / L"experiments/phase3/runtime/shared").u8string();
  std::string user = (root / L"experiments/phase3/runtime/user").u8string();
  std::string logs = user + "/logs";
  std::filesystem::create_directories(logs);
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = shared.c_str();
  traits.user_data_dir = user.c_str();
  traits.app_name = "rime.study-native-spike";
  traits.min_log_level = 2;
  traits.log_dir = logs.c_str();
  const char* modules[] = {"default", "lua", nullptr};
  traits.modules = modules;
  state.api->setup(&traits);
  state.api->initialize(&traits);
  state.initialized = true;
  state.session = state.api->create_session();
  return state.session && state.api->select_schema(state.session, "study");
}

bool Engine::Key(int key, int modifiers) {
  return impl_->api->process_key(impl_->session, key, modifiers) != 0;
}

void Engine::Type(const char* text) {
  impl_->api->clear_composition(impl_->session);
  for (; *text; ++text) Key(static_cast<unsigned char>(*text));
}

bool Engine::Select(size_t index) {
  return impl_->api->select_candidate_on_current_page(impl_->session, index) != 0;
}

bool Engine::Highlight(size_t index) {
  return RIME_API_AVAILABLE(impl_->api, highlight_candidate_on_current_page) &&
      impl_->api->highlight_candidate_on_current_page(impl_->session, index);
}

Snapshot Engine::Read() {
  auto& state = *impl_;
  Snapshot result;
  auto safe = [](const char* text) { return text ? text : ""; };
  result.input = safe(state.api->get_input(state.session));
  result.learning = state.api->get_option(state.session, "learning_mode") != 0;
  char action[128]{};
  state.api->get_property(state.session, "study_action", action, sizeof(action));
  result.action = action;
  RIME_STRUCT(RimeContext, context);
  if (state.api->get_context(state.session, &context)) {
    result.page = context.menu.page_no;
    result.last_page = context.menu.is_last_page != 0;
    result.highlighted = context.menu.highlighted_candidate_index;
    for (int i = 0; i < context.menu.num_candidates; ++i) {
      const auto& candidate = context.menu.candidates[i];
      result.candidates.push_back({safe(candidate.text), safe(candidate.comment)});
    }
    state.api->free_context(&context);
  }
  RIME_STRUCT(RimeCommit, commit);
  if (state.api->get_commit(state.session, &commit)) {
    result.commit = safe(commit.text);
    state.api->free_commit(&commit);
  }
  return result;
}

}  // namespace study

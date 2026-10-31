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
  SessionVersion version;

  bool Ready() const { return api && session; }

  std::string Property(const char* name) const {
    char buffer[4096]{};
    if (!Ready() || !api->get_property(session, name, buffer, sizeof(buffer)))
      return {};
    return buffer;
  }

  bool Request(const char* name) {
    if (!Ready() || Property("study_protocol") != "1") return false;
    api->set_property(session, "study_response", "");
    api->set_property(session, "study_target_text", "");
    api->set_property(session, "study_target_english", "");
    api->set_property(session, "study_target_reason", "");
    api->set_property(session, "study_request", name);
    const bool handled = api->process_key(session, 0, 0) != 0;
    api->set_property(session, "study_request", "");
    return handled && Property("study_response") == name;
  }

  bool Reject(const std::string& reason) {
    if (Ready()) api->set_property(session, "study_action", reason.c_str());
    return false;
  }

  Snapshot Read(bool consumeCommit) const {
    Snapshot result;
    result.version = version.Current();
    if (!Ready()) return result;
    auto safe = [](const char* text) { return text ? text : ""; };
    result.input = safe(api->get_input(session));
    result.caret = api->get_caret_pos(session);
    result.learning = api->get_option(session, "learning_mode") != 0;
    result.action = Property("study_action");
    RIME_STRUCT(RimeContext, context);
    if (api->get_context(session, &context)) {
      result.page = context.menu.page_no;
      result.last_page = context.menu.is_last_page != 0;
      result.highlighted = context.menu.highlighted_candidate_index;
      for (int i = 0; i < context.menu.num_candidates; ++i) {
        const auto& candidate = context.menu.candidates[i];
        result.candidates.push_back({safe(candidate.text), safe(candidate.comment)});
      }
      api->free_context(&context);
    }
    if (consumeCommit) {
      RIME_STRUCT(RimeCommit, commit);
      if (api->get_commit(session, &commit)) {
        result.commit = safe(commit.text);
        api->free_commit(&commit);
      }
    }
    return result;
  }

  ~Impl() {
    if (session) api->destroy_session(session);
    if (initialized) api->finalize();
    if (module) FreeLibrary(module);
  }
};

Engine::Engine() : impl_(std::make_unique<Impl>()) {}
Engine::~Engine() = default;

bool Engine::Open(const std::filesystem::path& root) {
  if (impl_->module) impl_ = std::make_unique<Impl>();
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
  return ResetSession();
}

bool Engine::Key(int key, int modifiers) {
  if (!impl_->Ready()) return false;
  InvalidateActions();
  return impl_->api->process_key(impl_->session, key, modifiers) != 0;
}

void Engine::Type(const char* text) {
  if (!impl_->Ready()) return;
  InvalidateActions();
  impl_->api->clear_composition(impl_->session);
  for (; *text; ++text) Key(static_cast<unsigned char>(*text));
}

bool Engine::Select(size_t index) {
  if (!impl_->Ready()) return false;
  InvalidateActions();
  return impl_->api->select_candidate_on_current_page(impl_->session, index) != 0;
}

bool Engine::Highlight(size_t index) {
  if (!impl_->Ready()) return false;
  const auto current = impl_->Read(false);
  if (index >= current.candidates.size()) return false;
  if (index == static_cast<size_t>(current.highlighted)) return true;
  InvalidateActions();
  return RIME_API_AVAILABLE(impl_->api, highlight_candidate_on_current_page) &&
      impl_->api->highlight_candidate_on_current_page(impl_->session, index);
}

EnglishTarget Engine::PrepareEnglish(size_t index) {
  auto& state = *impl_;
  EnglishTarget target;
  target.version = state.version.Current();
  target.index = index;
  if (!state.Ready()) { target.reason = "unavailable"; return target; }
  auto current = state.Read(false);
  if (index >= current.candidates.size()) return target;
  if (!Highlight(index)) { target.reason = "unavailable"; return target; }
  const bool inspected = state.Request("inspect-v1");
  current = state.Read(false); // Does not drain pending text for the application.
  target.version = state.version.Current();
  target.page = current.page;
  target.input = current.input;
  target.caret = current.caret;
  if (!inspected || index >= current.candidates.size() ||
      current.highlighted != static_cast<int>(index)) {
    target.reason = "unavailable";
    return target;
  }
  target.chinese = state.Property("study_target_text");
  target.english = state.Property("study_target_english");
  target.reason = state.Property("study_target_reason");
  if (target.chinese != current.candidates[index].text || target.reason.empty())
    target.reason = "unavailable";
  return target;
}

bool Engine::CommitEnglish(const EnglishTarget& target) {
  auto& state = *impl_;
  if (!state.Ready()) return false;
  if (!state.version.Matches(target.version)) return state.Reject("stale-candidate");
  const auto current = state.Read(false);
  if (target.index >= current.candidates.size() || target.page != current.page ||
      target.input != current.input || target.caret != current.caret ||
      static_cast<int>(target.index) != current.highlighted ||
      target.chinese != current.candidates[target.index].text)
    return state.Reject("stale-candidate");

  // Re-read the actual selected candidate and dictionary in Lua. No cached
  // comment, menu label or caller-supplied English becomes committed text.
  const auto verified = PrepareEnglish(target.index);
  if (!verified.Available()) return state.Reject(verified.reason);
  if (!target.Available() || verified.english != target.english)
    return state.Reject("stale-candidate");
  InvalidateActions();
  if (!state.Request("commit-v1")) return state.Reject("unavailable");
  return state.Property("study_action") == "english-committed";
}

void Engine::InvalidateActions() { impl_->version.Invalidate(); }

bool Engine::ResetSession() {
  auto& state = *impl_;
  state.version.Reset();
  if (!state.initialized) return false;
  if (state.session) state.api->destroy_session(state.session);
  state.session = state.api->create_session();
  if (state.session && !state.api->select_schema(state.session, "study")) {
    state.api->destroy_session(state.session);
    state.session = 0;
  }
  return state.session != 0;
}

Snapshot Engine::Read() { return impl_->Read(true); }

}  // namespace study

// SPDX-License-Identifier: GPL-3.0-or-later
#include "bridge.h"
#include <rime_api.h>
#include <rime/config.h>
#include <rime/dict/prism.h>
#include <rime/dict/reverse_lookup_dictionary.h>
#include <rime/dict/table.h>
#include <cstring>
#include <exception>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
RimeApi* api = nullptr;
bool initialized = false;
thread_local std::string error;

// Packaged sources are SHA-256 verified by DataDeployer before this call.
// Reuse deployed indexes only if every supported schema and binary can still
// be opened by Rime itself. Missing/corrupt builds take the full repair path;
// Rime's normal modification check still handles changed user configuration.
bool reusable_build(const char* directory) {
  try {
    const std::filesystem::path build(directory);
    rime::Config defaults;
    if (!defaults.LoadFromFile(build / "default.yaml") || !defaults.GetList("schema_list")) return false;
    const auto table_path = build / "cedict_study.table.bin";
    const auto reverse_path = build / "cedict_study.reverse.bin";
    if (!std::filesystem::is_regular_file(table_path) || std::filesystem::file_size(table_path) < 128 ||
        !std::filesystem::is_regular_file(reverse_path) || std::filesystem::file_size(reverse_path) < 128) return false;
    rime::Table table(table_path);
    rime::ReverseDb reverse(reverse_path);
    if (!table.Load() || !reverse.Load()) return false;
    for (const char* schema : {"study", "study_double_pinyin", "study_flypy"}) {
      rime::Config config;
      std::string id;
      if (!config.LoadFromFile(build / (std::string(schema) + ".schema.yaml")) ||
          !config.GetString("schema/schema_id", &id) || id != schema) return false;
      const auto prism_path = build / (std::string(schema) + ".prism.bin");
      if (!std::filesystem::is_regular_file(prism_path) || std::filesystem::file_size(prism_path) < 128) return false;
      rime::Prism prism(prism_path);
      if (!prism.Load() || prism.dict_file_checksum() != table.dict_file_checksum()) return false;
    }
    return true;
  } catch (...) {
    return false;
  }
}

bool valid(uintptr_t session) {
  if (!initialized || !session || !api->find_session(session)) {
    error = "invalid-session";
    return false;
  }
  return true;
}

template<typename F> int guarded(F action) noexcept {
  try { error.clear(); return action(); }
  catch (const std::exception&) { error = "native-exception"; }
  catch (...) { error = "unknown-native-exception"; }
  return -1;
}

char* copy(const char* text) {
  if (!text) return nullptr;
  const auto length = std::strlen(text);
  if (length > 1024 * 1024) throw std::runtime_error("oversize-native-text");
  auto output = std::make_unique<char[]>(length + 1);
  std::memcpy(output.get(), text, length + 1);
  return output.release();
}

struct OwnedView : StudyRimeView {
  std::string raw, composition;
  std::vector<std::string> text, comments;
  std::vector<StudyCandidate> entries;
};

struct ContextLease {
  RimeContext value{};
  bool acquired = false;
  ContextLease() { RIME_STRUCT_INIT(RimeContext, value); }
  ~ContextLease() { if (acquired) api->free_context(&value); }
};
struct CommitLease {
  RimeCommit value{};
  bool acquired = false;
  CommitLease() { RIME_STRUCT_INIT(RimeCommit, value); }
  ~CommitLease() { if (acquired) api->free_commit(&value); }
};
}

int study_rime_initialize(const char* shared, const char* user, const char* build) {
  return guarded([&] {
    if (initialized || !shared || !user || !build) return 0;
    api = rime_get_api();
    if (!RIME_API_AVAILABLE(api, change_page) || !RIME_API_AVAILABLE(api, highlight_candidate_on_current_page)) return 0;
    RIME_STRUCT(RimeTraits, traits);
    static const char* modules[] = {"default", "lua", nullptr};
    traits.shared_data_dir = shared;
    traits.user_data_dir = user;
    traits.prebuilt_data_dir = build;
    traits.staging_dir = build;
    traits.distribution_name = "StudyIME Android";
    traits.distribution_code_name = "studyime";
    traits.distribution_version = "0.1.0-preview.1";
    traits.app_name = "rime.studyime.android";
    traits.modules = modules;
    traits.min_log_level = 3;
    traits.log_dir = "";
    api->setup(&traits);
    api->initialize(&traits);
    initialized = true;
    if (api->start_maintenance(reusable_build(build) ? False : True)) api->join_maintenance_thread();
    return 1;
  });
}

void study_rime_finalize() {
  guarded([] {
    if (initialized) {
      api->join_maintenance_thread();
      api->cleanup_all_sessions();
      api->finalize();
      initialized = false;
    }
    return 1;
  });
}

uintptr_t study_rime_session() {
  uintptr_t result = 0;
  guarded([&] { if (initialized) result = api->create_session(); return result ? 1 : 0; });
  return result;
}
void study_rime_destroy_session(uintptr_t s) { guarded([&] { return valid(s) ? api->destroy_session(s) : 0; }); }
int study_rime_key(uintptr_t s, int key, int modifiers) { return guarded([&] { return valid(s) ? api->process_key(s, key, modifiers) : -1; }); }
int study_rime_select(uintptr_t s, size_t index) { return guarded([&] { return valid(s) ? api->select_candidate_on_current_page(s, index) : -1; }); }
int study_rime_highlight(uintptr_t s, size_t index, int absolute) { return guarded([&] { return valid(s) ? (absolute ? api->highlight_candidate(s, index) : api->highlight_candidate_on_current_page(s, index)) : -1; }); }
int study_rime_forget(uintptr_t s, size_t index) { return guarded([&] { return valid(s) ? api->delete_candidate_on_current_page(s, index) : -1; }); }
int study_rime_page(uintptr_t s, int back) { return guarded([&] { return valid(s) ? api->change_page(s, back) : -1; }); }
int study_rime_schema(uintptr_t s, const char* schema) { return guarded([&] { return valid(s) && schema ? api->select_schema(s, schema) : -1; }); }
int study_rime_option(uintptr_t s, const char* key, int value) { return guarded([&] { if (!valid(s) || !key) return -1; api->set_option(s, key, value); return api->get_option(s, key) == value ? 1 : 0; }); }
int study_rime_property(uintptr_t s, const char* key, const char* value) { return guarded([&] { if (!valid(s) || !key || !value) return -1; api->set_property(s, key, value); return 1; }); }
int study_rime_clear(uintptr_t s) { return guarded([&] { if (!valid(s)) return -1; api->clear_composition(s); return 1; }); }
int study_rime_caret(uintptr_t s, size_t caret) { return guarded([&] { if (!valid(s)) return -1; api->set_caret_pos(s, caret); return 1; }); }

const StudyRimeView* study_rime_read(uintptr_t s) {
  std::unique_ptr<OwnedView> result;
  const auto status = guarded([&] {
    if (!valid(s)) return -1;
    result = std::make_unique<OwnedView>();
    const auto input = api->get_input(s);
    result->raw = input ? input : "";
    result->caret = api->get_caret_pos(s);
    ContextLease lease;
    lease.acquired = api->get_context(s, &lease.value);
    const auto& ctx = lease.value;
    result->composition = ctx.composition.preedit ? ctx.composition.preedit : "";
    result->preedit_cursor = ctx.composition.cursor_pos;
    result->page = ctx.menu.page_no;
    result->page_size = ctx.menu.page_size;
    result->highlighted = ctx.menu.highlighted_candidate_index;
    result->last_page = ctx.menu.is_last_page;
    const auto count = ctx.menu.num_candidates;
    if (count < 0 || count > 128 || (count && !ctx.menu.candidates)) return -1;
    result->text.reserve(count);
    result->comments.reserve(count);
    result->entries.reserve(count);
    for (int i = 0; i < count; ++i) {
      result->text.emplace_back(ctx.menu.candidates[i].text ? ctx.menu.candidates[i].text : "");
      result->comments.emplace_back(ctx.menu.candidates[i].comment ? ctx.menu.candidates[i].comment : "");
    }
    for (int i = 0; i < count; ++i) result->entries.push_back({result->text[i].c_str(), result->comments[i].c_str()});
    result->input = result->raw.c_str();
    result->preedit = result->composition.c_str();
    result->candidate_count = result->entries.size();
    result->candidates = result->entries.data();
    return 1;
  });
  return status == 1 ? result.release() : nullptr;
}
void study_rime_free_view(const StudyRimeView* view) { delete static_cast<const OwnedView*>(view); }

char* study_rime_take_commit(uintptr_t s) {
  char* text = nullptr;
  guarded([&] {
    if (!valid(s)) return -1;
    CommitLease lease;
    lease.acquired = api->get_commit(s, &lease.value);
    if (lease.acquired) text = copy(lease.value.text);
    return 1;
  });
  return text;
}
char* study_rime_get_property(uintptr_t s, const char* key) {
  char* text = nullptr;
  guarded([&] {
    if (!valid(s) || !key) return -1;
    char buffer[4096]{};
    if (api->get_property(s, key, buffer, sizeof(buffer))) {
      buffer[sizeof(buffer) - 1] = 0;
      text = copy(buffer);
    }
    return 1;
  });
  return text;
}
void study_rime_free_text(char* text) { delete[] text; }
const char* study_rime_error() { return error.c_str(); }
const char* study_rime_version() { return api && RIME_API_AVAILABLE(api, get_version) ? api->get_version() : "uninitialized"; }

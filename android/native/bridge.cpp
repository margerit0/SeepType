// SPDX-License-Identifier: GPL-3.0-or-later
#include "bridge.h"
#include <rime_api.h>
#include <rime/config.h>
#include <rime/dict/prism.h>
#include <rime/dict/reverse_lookup_dictionary.h>
#include <rime/dict/table.h>
#include <rime/dict/table_db.h>
#include <rime/dict/user_dictionary.h>
#include <utf8.h>
#include <algorithm>
#include <charconv>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
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

rime::an<rime::Db> word_frequency_db() {
  auto dictionaries = dynamic_cast<rime::UserDictionaryComponent*>(
      rime::UserDictionary::Require("user_dictionary"));
  // The full-pinyin and both double-pinyin schemas share this database.
  auto db = dictionaries ? dictionaries->FindDb("cedict_study") : nullptr;
  if (!db || !db->loaded() || db->disabled()) throw std::runtime_error("user-dictionary-unavailable");
  return db;
}

std::map<std::string, int> read_word_frequency(const char* path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("word-frequency-unreadable");
  std::map<std::string, int> records;
  std::string line;
  for (bool first = true; std::getline(input, line); first = false) {
    std::string_view row(line);
    if (first && row.substr(0, 3) == "\xEF\xBB\xBF") row.remove_prefix(3);
    if (!row.empty() && row.back() == '\r') row.remove_suffix(1);
    if (row.empty() || row.front() == '#') continue;
    const auto word_end = row.find('\t');
    const auto pinyin_end = word_end == row.npos ? row.npos : row.find('\t', word_end + 1);
    if (pinyin_end == row.npos) throw std::runtime_error("invalid-word-frequency-row");
    const auto word = row.substr(0, word_end);
    const auto pinyin = row.substr(word_end + 1, pinyin_end - word_end - 1);
    const auto count_text = row.substr(pinyin_end + 1);
    int count;
    const auto parsed = std::from_chars(count_text.data(), count_text.data() + count_text.size(), count);
    if (word.empty() || !utf8::is_valid(word.begin(), word.end()) ||
        std::any_of(word.begin(), word.end(), [](unsigned char c) { return c < 32 || c == 127; }) ||
        pinyin.empty() || pinyin.front() == ' ' || pinyin.back() == ' ' ||
        pinyin.find_first_not_of("abcdefghijklmnopqrstuvwxyz ") != pinyin.npos || pinyin.find("  ") != pinyin.npos ||
        parsed.ec != std::errc{} || parsed.ptr != count_text.data() + count_text.size() || count < 0) {
      throw std::runtime_error("invalid-word-frequency-row");
    }
    auto& merged = records[std::string(pinyin) + " \t" + std::string(word)];
    merged = (std::max)(merged, count);
  }
  if (input.bad() || !input.eof()) throw std::runtime_error("word-frequency-unreadable");
  return records;
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

int study_rime_export_word_frequency(const char* path) {
  return guarded([&] {
    if (!initialized || !path) return -1;
    auto db = word_frequency_db();
    auto transaction = rime::As<rime::Transactional>(db);
    if (transaction && transaction->in_transaction() && !transaction->CommitTransaction()) return -1;
    auto records = db->QueryAll();
    if (!records) return -1;

    std::ofstream output;
    output.exceptions(std::ios::badbit | std::ios::failbit);
    output.open(path, std::ios::binary);
    output << "# Rime user dictionary export\n# word\tpinyin\tcount\n";
    int count = 0;
    std::string key, value;
    rime::Tsv row;
    while (records->GetNextRecord(&key, &value)) {
      if (!rime::TableDb::format.formatter(key, value, &row)) continue;
      output << row[0] << '\t' << row[1] << '\t' << row[2] << '\n';
      ++count;
    }
    output.close();
    return count;
  });
}

int study_rime_import_word_frequency(const char* path) {
  return guarded([&] {
    if (!initialized || !path) return -1;
    const auto records = read_word_frequency(path);
    if (records.empty()) return 0;
    auto db = word_frequency_db();
    auto transaction = rime::As<rime::Transactional>(db);
    if (!transaction || db->readonly() ||
        (transaction->in_transaction() && !transaction->CommitTransaction()) ||
        !transaction->BeginTransaction()) return -1;

    try {
      for (const auto& [key, count] : records) {
        std::string value;
        rime::UserDbValue entry;
        if (db->Fetch(key, &value)) {
          if (!entry.Unpack(value)) throw std::runtime_error("invalid-user-dictionary-entry");
          if (entry.commits >= count) continue;
        }
        entry.commits = count;
        // Use the initial weight of Rime's table import and preserve the local weight and tick.
        entry.dee = (std::max)(entry.dee, (count + 1.0) / 1e8);
        if (!db->Update(key, entry.Pack())) throw std::runtime_error("word-frequency-write-failed");
      }
    } catch (...) {
      transaction->AbortTransaction();
      throw;
    }
    return transaction->CommitTransaction() ? static_cast<int>(records.size()) : -1;
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

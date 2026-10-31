#pragma once

#include <filesystem>
#include <memory>
#include <string>
#include <vector>
#include "../../src/study/SessionActions.h"

namespace study {

struct Candidate {
  std::string text;
  std::string comment;
};

struct Snapshot {
  VersionStamp version;
  std::string input;
  std::string commit;
  std::string action;
  bool learning = false;
  bool last_page = false;
  int page = 0;
  int highlighted = 0;
  size_t caret = 0;
  std::vector<Candidate> candidates;
};

// Keep rime_api.h out of ATL translation units. Its .CRT$XCU declaration
// interferes with selectany initializers in this MSVC 19.29 toolchain.
// This host-only boundary does not change librime or Weasel's IPC.
class Engine {
 public:
  Engine();
  ~Engine();
  bool Open(const std::filesystem::path& root);
  bool Key(int key, int modifiers = 0);
  void Type(const char* text);
  bool Select(size_t index);
  bool Highlight(size_t index);
  EnglishTarget PrepareEnglish(size_t index);
  bool CommitEnglish(const EnglishTarget& target);
  void InvalidateActions();
  bool ResetSession();
  Snapshot Read();

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace study

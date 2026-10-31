#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace study {

struct VersionStamp {
  std::uint64_t session = 0;
  std::uint64_t revision = 0;
};

// One instance per live input session, accessed on its serialized event thread.
// A recreated session gets a new identity even when its candidates are identical.
class SessionVersion {
 public:
  SessionVersion();
  SessionVersion(const SessionVersion&) = delete;
  SessionVersion& operator=(const SessionVersion&) = delete;
  void Reset();
  void Invalidate();
  VersionStamp Current() const { return stamp_; }
  bool Matches(VersionStamp other) const;

 private:
  VersionStamp stamp_;
};

// Ephemeral UI data, never a second dictionary or a persisted input history.
// The engine must revalidate this target before dispatching an English action.
struct EnglishTarget {
  VersionStamp version;
  std::size_t index = 0;
  int page = 0;
  std::size_t caret = 0;
  std::string input;
  std::string chinese;
  std::string english;
  std::string reason = "no-candidate";
  bool Available() const { return reason == "ready" && !english.empty(); }
};

}  // namespace study

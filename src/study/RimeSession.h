#pragma once

#include "SessionActions.h"
#include <memory>

namespace study {

// Non-owning adapter for an existing Rime session. Only the owning service
// creates/destroys sessions and consumes commits. Keep rime_api.h out of ATL.
class RimeSession {
 public:
  RimeSession(void* api, std::uintptr_t session);
  ~RimeSession();
  RimeSession(const RimeSession&) = delete;
  RimeSession& operator=(const RimeSession&) = delete;

  VersionStamp Version() const;
  void Invalidate();
  bool Learning() const;
  bool SetLearning(bool enabled);
  EnglishTarget Inspect(std::size_t index);
  bool Commit(const EnglishTarget& target);
  bool Forget(const EnglishTarget& target);

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace study

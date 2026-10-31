#pragma once

#include "RimeSession.h"
#include "StudyProtocol.h"
#include <map>
#include <optional>

namespace study {

// All calls must run on the Weasel handler's serialized event path.
class StudyService {
 public:
  StudyService();
  void Attach(std::uint32_t ipc, void* api, std::uintptr_t rimeSession);
  void Remove(std::uint32_t ipc);
  void Clear();
  void Invalidate(std::uint32_t ipc);
  void Activate(std::uint32_t ipc);
  void FocusOut(std::uint32_t ipc);
  ActionState State(std::uint32_t ipc) const;
  bool Apply(std::uint32_t ipc, const ActionRequest& request);

 private:
  struct Session {
    std::unique_ptr<RimeSession> rime;
    std::optional<EnglishTarget> target;
    std::string reason = "snapshot";
  };
  std::uint64_t identity_;
  std::uint32_t active_ = 0;
  std::map<std::uint32_t, Session> sessions_;
};

}  // namespace study

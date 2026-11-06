#include "StudyService.h"
#include <random>

namespace study {

StudyService::StudyService() {
  // Distinguish process/service restarts even if Windows reuses an IPC id.
  std::random_device random;
  do {
    identity_ = (static_cast<std::uint64_t>(random()) << 32) | random();
  } while (!identity_);
}

void StudyService::Attach(std::uint32_t ipc, void* api, std::uintptr_t rimeSession) {
  if (!ipc || !api || !rimeSession) return;
  Session session;
  session.rime = std::make_unique<RimeSession>(api, rimeSession);
  sessions_[ipc] = std::move(session);
  Activate(ipc);
}

void StudyService::Remove(std::uint32_t ipc) {
  sessions_.erase(ipc);
  if (active_ == ipc) active_ = 0;
}
void StudyService::Clear() { sessions_.clear(); active_ = 0; }

void StudyService::Invalidate(std::uint32_t ipc) {
  const auto found = sessions_.find(ipc);
  if (found == sessions_.end()) return;
  found->second.rime->Invalidate();
  found->second.target.reset();
  found->second.reason = "snapshot";
}

void StudyService::Activate(std::uint32_t ipc) {
  if (!sessions_.count(ipc) || active_ == ipc) return;
  Invalidate(active_);
  Invalidate(ipc);
  active_ = ipc;
}

void StudyService::FocusOut(std::uint32_t ipc) {
  Invalidate(ipc);
  if (active_ == ipc) active_ = 0;
}

ActionState StudyService::State(std::uint32_t ipc) const {
  ActionState state;
  const auto found = sessions_.find(ipc);
  if (found == sessions_.end()) return state;
  const auto& session = found->second;
  state.stamp = {identity_, session.rime->Version()};
  state.learning = session.rime->Learning();
  state.reason = active_ == ipc ? session.reason : "inactive-session";
  if (session.target && active_ == ipc) {
    state.index = static_cast<std::uint32_t>(session.target->index);
    state.chinese = session.target->chinese;
    state.english = session.target->english;
  }
  return state;
}

bool StudyService::Apply(std::uint32_t ipc, const ActionRequest& request) {
  const auto found = sessions_.find(ipc);
  if (found == sessions_.end() || active_ != ipc) return false;
  auto& session = found->second;
  const auto current = session.rime->Version();
  if (request.stamp.service != identity_ ||
      request.stamp.version.session != current.session ||
      request.stamp.version.revision != current.revision) {
    session.target.reset();
    session.reason = "stale-candidate";
    return false;
  }
  switch (request.action) {
    case Action::Inspect: {
      session.target = session.rime->Inspect(request.index);
      if (session.target->chinese.size() > kMaxDefinitionBytes ||
          session.target->english.size() > kMaxDefinitionBytes) {
        session.target.reset(); session.reason = "unavailable"; return false;
      }
      session.reason = session.target->reason;
      return true;
    }
    case Action::CommitEnglish: {
      if (!session.target || session.target->index != request.index) {
        session.reason = "stale-candidate";
        return false;
      }
      const auto target = *session.target;
      session.target.reset();
      const bool committed = session.rime->Commit(target);
      session.reason = committed ? "english-committed" :
          target.Available() ? "stale-candidate" : target.reason;
      return committed;
    }
    case Action::SetLearning: {
      session.target.reset();
      const bool changed = session.rime->SetLearning(request.enabled);
      session.reason = changed ? "learning-changed" : "unavailable";
      return changed;
    }
  }
  return false;
}

}  // namespace study

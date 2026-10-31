#include "SessionActions.h"
#include <atomic>

namespace study {
namespace {
std::atomic<std::uint64_t> nextSession{0};
}

SessionVersion::SessionVersion() { Reset(); }

void SessionVersion::Reset() {
  stamp_ = {++nextSession, 1};
}

void SessionVersion::Invalidate() {
  if (++stamp_.revision == 0) Reset();
}

bool SessionVersion::Matches(VersionStamp other) const {
  return other.session != 0 && other.session == stamp_.session &&
         other.revision == stamp_.revision;
}

}  // namespace study

#include "StudyMotion.h"
#include <algorithm>

namespace study {
double StudyMotion::Ease(double progress) {
  const double x = std::clamp(progress, 0.0, 1.0);
  double lo = 0, hi = 1;
  for (int i = 0; i < 24; ++i) {
    const double t = (lo + hi) / 2, s = 1 - t;
    const double bx = 3 * s * s * t * .22 + 3 * s * t * t * .36 + t * t * t;
    if (bx < x) lo = t; else hi = t;
  }
  const double t = (lo + hi) / 2, s = 1 - t;
  return 3 * s * s * t + 3 * s * t * t + t * t * t;
}
void StudyMotion::Reset(bool learning) {
  from_ = target_ = alphaFrom_ = learning ? 1 : 0;
  mode_ = page_ = false;
}
void StudyMotion::SetLearning(bool learning, std::uint64_t now, bool reduced) {
  const auto current = At(now);
  from_ = current.learning; alphaFrom_ = current.englishAlpha;
  target_ = learning ? 1 : 0;
  modeStart_ = now; mode_ = !reduced && from_ != target_;
  page_ = false;
  if (reduced) from_ = alphaFrom_ = target_;
}
void StudyMotion::Page(int direction, std::uint64_t now, bool reduced) {
  pageStart_ = now; direction_ = direction < 0 ? -1 : 1; page_ = !reduced;
}
void StudyMotion::CancelPage() { page_ = false; }
void StudyMotion::Finish() { from_ = alphaFrom_ = target_; mode_ = page_ = false; }
MotionFrame StudyMotion::At(std::uint64_t now) const {
  MotionFrame result;
  const auto modeElapsed = now >= modeStart_ ? now - modeStart_ : 0;
  const auto pageElapsed = now >= pageStart_ ? now - pageStart_ : 0;
  result.learning = mode_ ? from_ + (target_ - from_) * Ease(modeElapsed / 240.0) : target_;
  result.englishAlpha = mode_ ? alphaFrom_ + (target_ - alphaFrom_) * Ease(modeElapsed / 160.0) : target_;
  if (page_ && pageElapsed < 180) {
    const double enter = Ease(pageElapsed / 180.0), leave = Ease(pageElapsed / 120.0);
    result.incomingX = direction_ * 10 * (1 - enter);
    result.outgoingX = -direction_ * 10 * leave;
    result.incomingAlpha = enter;
    result.outgoingAlpha = 1 - leave;
  }
  result.active = (mode_ && modeElapsed < 240) || (page_ && pageElapsed < 180);
  return result;
}
}

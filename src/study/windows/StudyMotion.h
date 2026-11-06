#pragma once
#include <cstdint>

namespace study {
struct MotionFrame {
  double learning = 1, englishAlpha = 1;
  double incomingX = 0, outgoingX = 0, incomingAlpha = 1, outgoingAlpha = 0;
  bool active = false;
};
// Pure time-based state; no timers or input queues, so rapid changes replace
// the previous transition and never delay authoritative candidate updates.
class StudyMotion {
 public:
  void Reset(bool learning);
  void SetLearning(bool learning, std::uint64_t now, bool reduced);
  void Page(int direction, std::uint64_t now, bool reduced);
  void CancelPage();
  void Finish();
  MotionFrame At(std::uint64_t now) const;
  static double Ease(double progress);
 private:
  double from_ = 1, target_ = 1, alphaFrom_ = 1;
  std::uint64_t modeStart_ = 0, pageStart_ = 0;
  bool mode_ = false, page_ = false;
  int direction_ = 1;
};
}

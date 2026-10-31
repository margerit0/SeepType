#pragma once
#include "StandardLayout.h"

namespace weasel {
// Test observer receives only this panel's generated frame, never the desktop.
void CaptureStudyFrame(HDC dc, int width, int height);

// Spike-only layout. No new IPC fields or changes to the Rime engine.
class StudyLayout : public StandardLayout {
 public:
  StudyLayout(const UIStyle& style, const Context& context, const Status& status, PDWR resources)
      : StandardLayout(style, context, status, resources) {}
  void DoLayout(CDCHandle dc, PDWR resources) override;
};
}

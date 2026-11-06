#pragma once
#include <atlbase.h>
#include <atlwin.h>
#include <wtl/atlapp.h>
#include <wtl/atlgdi.h>
#include <wtl/atlmisc.h>
#include <StandardLayout.h>

namespace study {
// Promoted from phase3/StudyLayout: the same DirectWrite measurements and
// shared two-line hit rectangles, plus a fixed viewport and right-side tools.
class StudyLayout : public weasel::StandardLayout {
 public:
  StudyLayout(const weasel::UIStyle& style, const weasel::Context& context,
      const weasel::Status& status, weasel::PDWR resources, double learning,
      double viewportDip = 0, double scrollDip = 0, bool largeText = false)
      : StandardLayout(style, context, status, resources), learning_(learning),
        viewportDip_(viewportDip), scrollDip_(scrollDip), large_(largeText) {}
  void DoLayout(CDCHandle dc, weasel::PDWR resources) override;
  int Hit(POINT point) const;
  bool ShouldDisplayStatusIcon() const override { return false; }
  bool IsInlinePreedit() const override { return true; }
  CRect viewport, tools[4];
  double naturalWidthDip = 0;
  static constexpr int Previous = -2, Next = -3, Learning = -4, More = -5, None = -1;
 private:
  double learning_, viewportDip_, scrollDip_;
  bool large_;
};
}

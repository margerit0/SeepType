// The product service keeps Rime presentation state; its TSF frontend owns the
// v0.5 CandidateUi windows. The service has never called the legacy UI::Create.
// Retain the uncreated-UI behavior without linking the old WTL window backend.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <WeaselUI.h>

namespace weasel {
bool UI::Create(HWND) { return false; }
void UI::Destroy(bool) { pDWR.reset(); }
bool UI::GetIsReposition() { return false; }
void UI::Show() {}
void UI::Hide() {}
void UI::ShowWithTimeout(size_t) {}
bool UI::IsCountingDown() const { return false; }
bool UI::IsShown() const { return false; }
void UI::Refresh() {}
void UI::UpdateInputPosition(RECT const&) {}
void UI::Update(const Context& context, const Status& status) {
  if (ctx_ == context && status_ == status) return;
  ctx_ = context;
  status_ = status;
  if (style_.candidate_abbreviate_length > 0) {
    const auto limit = static_cast<size_t>(style_.candidate_abbreviate_length);
    for (auto& candidate : ctx_.cinfo.candies) {
      if (candidate.str.size() > limit)
        candidate.str = candidate.str.substr(0, limit - 1) + L"..." + candidate.str.back();
    }
  }
}
}

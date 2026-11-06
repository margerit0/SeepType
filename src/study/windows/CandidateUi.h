#pragma once
#include <WeaselUI.h>
#include "StudyLayout.h"
#include "StudyMotion.h"
#include "UiPreferences.h"
#include "../StudyProtocol.h"
#include <cstdint>

namespace study {
struct CandidateAccessBinding;
struct CandidateFrame {
  int width = 0, height = 0;
  std::vector<std::uint8_t> bgra;
};

// The TSF-owned candidate view. It reuses Weasel's DirectWrite resources and
// the promoted StudyLayout; engine actions still go through Weasel callbacks.
class CandidateUi {
 public:
  CandidateUi();
  ~CandidateUi();
  bool Create(HWND parent);
  void Destroy(bool full = false);
  void Show();
  void Hide();
  bool IsShown() const;
  bool GetIsReposition() const { return false; }
  void Update(const weasel::Context& context, const weasel::Status& status);
  void UpdateInputPosition(const RECT& rectangle);
  void Present(const ActionState& state, bool capability);
  void Invalidate();
  void InputKey(WPARAM key, bool release);
  bool ReloadPreferences();
  bool SaveLearning(bool enabled);
  bool ShowSettings(HWND owner);
  const UiPreferences& Preferences() const { return preferences_; }
  void ShowDefinition(const ActionState& target, unsigned index, bool pinned);
  void HideDefinition();
  bool DefinitionVisible() const;
  POINT MenuPosition(unsigned index) const;
  void Invoke(int hit);
  std::wstring AccessibleName(int hit) const;
  bool Enabled(int hit) const;
  CRect HitRectangle(int hit) const;
  HWND Window() const { return window_; }
  const StudyLayout* Geometry() const { return layout_.get(); }
  // Same drawing routine used by the live view and by offscreen render checks.
  CandidateFrame Render(std::uint64_t now);
  void SetRenderEnvironment(UINT dpi, int workWidthDip, bool reducedMotion);
  weasel::Context& ctx() { return context_; }
  weasel::Status& status() { return status_; }
  weasel::UIStyle& style() { return style_; }
  std::function<void(unsigned, HWND, POINT)> studyMenu;
  std::function<void(bool)> studyLearning;
  std::function<void(unsigned, bool)> studyDetail;
  std::function<bool()> studyPoll;
  std::function<void(bool, const CandidateFrame&)> frameObserver;
  std::function<void(bool)> accessibilityLifetime;
  std::function<void(size_t* const, size_t* const, bool* const, bool* const)>& uiCallback() { return callback_; }
  void SetUICallBack(const std::function<void(size_t* const, size_t* const, bool* const, bool* const)>& value) { callback_ = value; }
 private:
  static LRESULT CALLBACK WindowProc(HWND, UINT, WPARAM, LPARAM);
  static LRESULT CALLBACK DetailProc(HWND, UINT, WPARAM, LPARAM);
  void ConfigureResources();
  void Layout(std::uint64_t now, bool revealSelection = false);
  void Paint();
  CandidateFrame RenderDefinition();
  void PaintDefinition();
  void Position();
  bool Reduced() const;
  void Text(const std::wstring&, const CRect&, IDWriteTextFormat1*, COLORREF, double alpha = 1, bool wrap = false);
  void Round(const CRect&, COLORREF, float radius, double alpha = 1, bool border = false);
  void DrawPage(const weasel::Context&, StudyLayout&, double x, double alpha, double englishAlpha);
  void SetColor(COLORREF color, double alpha = 1);
  void CloseWindows();
  HWND window_ = nullptr, owner_ = nullptr, detail_ = nullptr;
  UINT dpi_ = 96;
  int workWidth_ = 1600, hover_ = StudyLayout::None, pressed_ = StudyLayout::None;
  int detailScroll_ = 0, detailContentHeight_ = 0;
  std::uint64_t pressedRevision_ = 0, revision_ = 0, hoverStart_ = 0, lastPoll_ = 0;
  bool capable_ = false, snapshotCurrent_ = false, learning_ = true, active_ = false, newInput_ = true, detailPinned_ = false;
  bool reducedOverride_ = false, renderEnvironment_ = false, dirtyResources_ = true;
  bool pointerInside_ = false;
  bool frameWasActive_ = false;
  double viewportDip_ = 0, scrollDip_ = 0, oldScrollDip_ = 0;
  RECT anchor_{};
  POINT position_{};
  UiPreferences preferences_;
  UiPreferences loadedPreferences_;
  ActionState action_, definition_;
  weasel::Context context_, previous_;
  std::vector<weasel::Text> collapseComments_;
  weasel::Status status_;
  weasel::UIStyle style_;
  weasel::PDWR resources_;
  std::unique_ptr<StudyLayout> layout_;
  std::shared_ptr<CandidateAccessBinding> access_;
  StudyMotion motion_;
  std::function<void(size_t* const, size_t* const, bool* const, bool* const)> callback_;
};
}

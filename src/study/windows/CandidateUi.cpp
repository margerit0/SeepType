#include "stdafx.h"
#include "CandidateUi.h"
#include "CandidateAccessibility.h"
#include <windowsx.h>
#include <algorithm>
#include <cmath>

namespace study {
namespace {
const wchar_t* CandidateClass = L"StudyImeCandidateV05";
const wchar_t* DefinitionClass = L"StudyImeDefinitionV05";
HMODULE Module() {
  HMODULE module = nullptr;
  GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
      reinterpret_cast<LPCWSTR>(&Module), &module);
  return module;
}
UINT WindowDpi(HWND window) {
  const auto query = reinterpret_cast<UINT(WINAPI*)(HWND)>(GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForWindow"));
  return query && window ? query(window) : 96;
}
std::wstring Wide(const std::string& text) {
  if (text.empty()) return {};
  const int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), nullptr, 0);
  if (!n) return {};
  std::wstring out(n, 0);
  MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), out.data(), n);
  return out;
}
struct Surface {
  HDC dc = nullptr;
  HBITMAP bitmap = nullptr;
  HGDIOBJ previous = nullptr;
  void* pixels = nullptr;
  int width, height;
  Surface(int w, int h) : width(w), height(h) {
    if (w <= 0 || h <= 0 || w > 16384 || h > 16384) return;
    BITMAPINFO info{}; info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = w; info.bmiHeader.biHeight = -h;
    info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32;
    dc = CreateCompatibleDC(nullptr);
    bitmap = CreateDIBSection(nullptr, &info, DIB_RGB_COLORS, &pixels, nullptr, 0);
    if (dc && bitmap) previous = SelectObject(dc, bitmap);
  }
  ~Surface() {
    if (previous) SelectObject(dc, previous);
    if (bitmap) DeleteObject(bitmap);
    if (dc) DeleteDC(dc);
  }
  CandidateFrame Copy() const {
    CandidateFrame out;
    if (!previous || !pixels) return out;
    GdiFlush(); out.width = width; out.height = height;
    const auto* data = static_cast<const std::uint8_t*>(pixels);
    out.bgra.assign(data, data + static_cast<size_t>(width) * height * 4);
    return out;
  }
};
void Display(HWND window, const CandidateFrame& frame, POINT at) {
  if (!window || frame.bgra.empty()) return;
  Surface surface(frame.width, frame.height);
  if (!surface.pixels || !surface.previous) return;
  memcpy(surface.pixels, frame.bgra.data(), frame.bgra.size());
  SIZE size{frame.width, frame.height}; POINT origin{};
  BLENDFUNCTION blend{AC_SRC_OVER, 0, 255, AC_SRC_ALPHA};
  UpdateLayeredWindow(window, nullptr, &at, &size, surface.dc, &origin, 0, &blend, ULW_ALPHA);
}
CRect Shift(CRect rectangle, int x) { rectangle.OffsetRect(x, 0); return rectangle; }
}

CandidateUi::CandidateUi() : preferences_(LoadPreferences(PreferencesPath())), loadedPreferences_(preferences_) {
  learning_ = preferences_.learning;
  motion_.Reset(learning_);
}
CandidateUi::~CandidateUi() {
  CloseWindows();
  UnregisterClassW(CandidateClass, Module());
  UnregisterClassW(DefinitionClass, Module());
}
bool CandidateUi::Create(HWND parent) {
  owner_ = parent;
  if (window_) {
    SetWindowLongPtrW(window_, GWLP_HWNDPARENT, reinterpret_cast<LONG_PTR>(parent));
    return true;
  }
  access_ = std::make_shared<CandidateAccessBinding>(); access_->view = this;
  WNDCLASSW cls{}; cls.hInstance = Module(); cls.lpszClassName = CandidateClass;
  cls.lpfnWndProc = WindowProc; cls.hCursor = LoadCursor(nullptr, IDC_ARROW);
  if (!RegisterClassW(&cls) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) return false;
  window_ = CreateWindowExW(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_LAYERED,
      CandidateClass, L"英语学习候选", WS_POPUP, 0, 0, 1, 1, parent, nullptr, cls.hInstance, this);
  if (window_ && !renderEnvironment_) {
    dpi_ = WindowDpi(window_);
    dirtyResources_ = true;
  }
  return window_ != nullptr;
}
void CandidateUi::CloseWindows() {
  if (access_) access_->view = nullptr;
  if (detail_) DestroyWindow(detail_);
  if (window_) DestroyWindow(window_);
  detail_ = window_ = nullptr;
}
void CandidateUi::Destroy(bool full) {
  CloseWindows();
  active_ = false; capable_ = snapshotCurrent_ = false; newInput_ = true;
  pressed_ = hover_ = StudyLayout::None;
  context_ = {}; previous_ = {}; status_ = {}; collapseComments_.clear(); layout_.reset();
  viewportDip_ = scrollDip_ = 0;
  motion_.Reset(learning_);
  if (full) resources_.reset();
}
void CandidateUi::Show() {
  if (!window_ || !status_.composing || context_.cinfo.empty()) return;
  Paint(); ShowWindow(window_, SW_SHOWNOACTIVATE);
  SetTimer(window_, 1, 16, nullptr);
}
void CandidateUi::Hide() {
  HideDefinition();
  if (window_) { KillTimer(window_, 1); ShowWindow(window_, SW_HIDE); }
  motion_.Finish(); previous_ = {};
}
bool CandidateUi::IsShown() const { return window_ && IsWindowVisible(window_); }
bool CandidateUi::Reduced() const { return renderEnvironment_ ? reducedOverride_ : ReducedMotion(preferences_); }
void CandidateUi::SetRenderEnvironment(UINT dpi, int width, bool reduced) {
  renderEnvironment_ = true; reducedOverride_ = reduced; dpi_ = dpi;
  workWidth_ = (std::max)(width, 200); dirtyResources_ = true;
}
bool CandidateUi::ReloadPreferences() {
  const auto path = PreferencesPath();
  if (path.empty()) return false;
  const auto loaded = LoadPreferences(path);
  // If a write failed, an unchanged file must not undo the in-memory choice.
  if (loaded == loadedPreferences_) return false;
  preferences_ = loadedPreferences_ = loaded; dirtyResources_ = true;
  motion_.Finish(); previous_ = {}; viewportDip_ = scrollDip_ = 0;
  return true;
}
bool CandidateUi::SaveLearning(bool enabled) {
  preferences_.learning = enabled;
  const bool saved = SavePreferences(PreferencesPath(), preferences_);
  if (saved) loadedPreferences_ = preferences_;
  return saved;
}
bool CandidateUi::ShowSettings(HWND owner) {
  if (status_.composing || active_) return false;
  HideDefinition();
  if (!EditPreferences(owner, PreferencesPath(), preferences_)) return false;
  loadedPreferences_ = preferences_;
  dirtyResources_ = true;
  return true;
}
void CandidateUi::Present(const ActionState& action, bool capability) {
  action_ = action; capable_ = capability; snapshotCurrent_ = true;
  if (!capability || !action.learning) HideDefinition();
}
void CandidateUi::Invalidate() {
  capable_ = snapshotCurrent_ = false;
  pressed_ = StudyLayout::None;
  HideDefinition();
  if (window_) SetWindowTextW(window_, L"英语学习候选");
}
void CandidateUi::InputKey(WPARAM key, bool release) {
  if (release || key == VK_SHIFT || key == VK_CONTROL || key == VK_MENU) return;
  if (key == VK_PRIOR || key == VK_NEXT || key == VK_UP || key == VK_DOWN) return;
  if (key == VK_F2 || key == VK_APPS || key == VK_F10) return;
  motion_.CancelPage(); previous_ = {};
  if ((key >= 'A' && key <= 'Z') || key == VK_BACK || key == VK_DELETE || key == VK_OEM_7 || key == VK_ESCAPE)
    newInput_ = true;
}
void CandidateUi::ConfigureResources() {
  if (!dirtyResources_ && resources_) return;
  const bool dark = DarkAppearance(preferences_);
  style_.layout_type = weasel::UIStyle::LAYOUT_HORIZONTAL;
  style_.inline_preedit = true; style_.client_caps |= weasel::INLINE_PREEDIT_CAPABLE;
  style_.max_width = style_.max_height = 0;
  style_.font_face = L"Microsoft YaHei UI"; style_.comment_font_face = style_.label_font_face = L"Segoe UI";
  style_.font_point = 13; style_.label_font_point = 10; style_.comment_font_point = 9;
  style_.antialias_mode = weasel::UIStyle::GRAYSCALE;
  style_.back_color = dark ? 0xff242220 : 0xfffafafa;
  style_.border_color = dark ? 0xff4d4741 : 0xffe3ded9;
  style_.candidate_text_color = dark ? 0xffeee8e2 : 0xff2b2520;
  style_.hilited_candidate_text_color = style_.candidate_text_color;
  style_.label_text_color = style_.comment_text_color = dark ? 0xffb4aaa0 : 0xff6d6359;
  style_.hilited_comment_text_color = dark ? 0xffffbe85 : 0xff9a5b24;
  style_.hilited_candidate_back_color = dark ? 0xff574330 : 0xfffff2e9;
  HIGHCONTRASTW contrast{sizeof(contrast)};
  if (SystemParametersInfoW(SPI_GETHIGHCONTRAST, sizeof(contrast), &contrast, 0) && (contrast.dwFlags & HCF_HIGHCONTRASTON)) {
    style_.back_color = GetSysColor(COLOR_WINDOW) | 0xff000000;
    style_.candidate_text_color = style_.label_text_color = style_.comment_text_color = GetSysColor(COLOR_WINDOWTEXT) | 0xff000000;
    style_.border_color = style_.candidate_text_color;
    style_.hilited_candidate_back_color = GetSysColor(COLOR_HIGHLIGHT) | 0xff000000;
    style_.hilited_comment_text_color = GetSysColor(COLOR_HIGHLIGHTTEXT) | 0xff000000;
    style_.hilited_candidate_text_color = style_.hilited_comment_text_color;
  }
  resources_ = std::make_shared<weasel::DirectWriteResources>(style_, dpi_);
  if (!resources_->pDWFactory || !resources_->pRenderTarget) return;
  const float scale = dpi_ / 96.0f, add = preferences_.largeText ? 2.0f : 0.0f;
  auto font = [&](const wchar_t* family, float size, float line, float baseline, ComPtr<IDWriteTextFormat1>& destination) {
    ComPtr<IDWriteTextFormat> format;
    if (SUCCEEDED(resources_->pDWFactory->CreateTextFormat(family, nullptr, DWRITE_FONT_WEIGHT_NORMAL,
        DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_STRETCH_NORMAL, size * scale, L"zh-CN", &format))) {
      format->SetWordWrapping(DWRITE_WORD_WRAPPING_NO_WRAP);
      format->SetLineSpacing(DWRITE_LINE_SPACING_METHOD_UNIFORM, line * scale, baseline * scale);
      format.As(&destination);
    }
  };
  font(L"Microsoft YaHei UI", 18 + add, 24 + add, 19 + add, resources_->pTextFormat);
  font(L"Segoe UI", 14 + add, 24 + add, 19 + add, resources_->pLabelTextFormat);
  font(L"Segoe UI", 12 + add, 16 + add, 12.5f + add, resources_->pCommentTextFormat);
  DWRITE_TRIMMING trim{DWRITE_TRIMMING_GRANULARITY_CHARACTER, 0, 0};
  ComPtr<IDWriteInlineObject> ellipsis;
  resources_->pDWFactory->CreateEllipsisTrimmingSign(resources_->pCommentTextFormat.Get(), &ellipsis);
  resources_->pCommentTextFormat->SetTrimming(&trim, ellipsis.Get());
  // Geometry, glyph sizes and the DIB already use physical pixels. Keep the
  // render target at 1:1 so Direct2D does not apply the monitor scale twice.
  resources_->pRenderTarget->SetDpi(96, 96);
  dirtyResources_ = false;
}
void CandidateUi::Layout(std::uint64_t now, bool reveal) {
  ConfigureResources();
  if (!resources_ || !resources_->pTextFormat) return;
  const auto frame = motion_.At(now);
  auto make = [&] {
    layout_ = std::make_unique<StudyLayout>(style_, context_, status_, resources_, frame.learning,
        viewportDip_, scrollDip_, preferences_.largeText);
    layout_->DoLayout(nullptr, resources_);
  };
  make();
  if (viewportDip_ <= 0) {
    viewportDip_ = (std::min)(layout_->naturalWidthDip, static_cast<double>((std::max)(96, workWidth_ - 124)));
    viewportDip_ = (std::max)(viewportDip_, 40.0);
    make();
  }
  const double maxScroll = (std::max)(0.0, layout_->naturalWidthDip - viewportDip_);
  const double before = scrollDip_;
  scrollDip_ = (std::clamp)(scrollDip_, 0.0, maxScroll);
  if (reveal && !context_.cinfo.empty()) {
    const auto rc = layout_->GetCandidateRect((std::clamp)(context_.cinfo.highlighted, 0, static_cast<int>(context_.cinfo.candies.size()) - 1));
    const double scale = dpi_ / 96.0;
    if (rc.left < layout_->viewport.left) scrollDip_ += (rc.left - layout_->viewport.left) / scale;
    else if (rc.right > layout_->viewport.right && rc.Width() <= layout_->viewport.Width())
      scrollDip_ += (rc.right - layout_->viewport.right) / scale;
    scrollDip_ = (std::clamp)(scrollDip_, 0.0, maxScroll);
  }
  if (before != scrollDip_) make();
}
void CandidateUi::Update(const weasel::Context& context, const weasel::Status& status) {
  const auto now = GetTickCount64();
  const bool enabled = capable_ && action_.learning;
  const bool changed = context_ != context || !(status_ == status) || learning_ != enabled;
  const bool starting = !active_ && status.composing;
  const bool paging = active_ && !newInput_ && status.composing &&
      context.cinfo.currentPage != context_.cinfo.currentPage && learning_ == enabled;
  if (newInput_) { viewportDip_ = scrollDip_ = 0; motion_.CancelPage(); previous_ = {}; }
  if (starting) { viewportDip_ = scrollDip_ = 0; motion_.Reset(enabled); previous_ = {}; }
  else if (learning_ != enabled) {
    motion_.SetLearning(enabled, now, Reduced()); previous_ = {}; HideDefinition();
  } else if (paging) {
    previous_ = context_; oldScrollDip_ = scrollDip_;
    motion_.Page(context.cinfo.currentPage > context_.cinfo.currentPage ? 1 : -1, now, Reduced());
    scrollDip_ = 0; HideDefinition();
  } else if (newInput_) {
    viewportDip_ = scrollDip_ = 0; motion_.CancelPage(); previous_ = {}; HideDefinition();
  }
  // Disabled Rime responses may contain unrelated upstream comments. The
  // collapsing visual retains only the previous verified English strings.
  const bool sameCandidates = context_.cinfo.candies.size() == context.cinfo.candies.size() &&
      std::equal(context_.cinfo.candies.begin(), context_.cinfo.candies.end(), context.cinfo.candies.begin(),
          [](const weasel::Text& a, const weasel::Text& b) { return a.str == b.str; });
  if (learning_) collapseComments_ = context_.cinfo.comments;
  if (!sameCandidates) collapseComments_.clear();
  context_ = context; status_ = status;
  if (!enabled) {
    context_.cinfo.comments.clear();
    context_.cinfo.comments.resize(context_.cinfo.candies.size());
    if (collapseComments_.size() == context_.cinfo.comments.size() && motion_.At(now).englishAlpha > 0)
      context_.cinfo.comments = collapseComments_;
  }
  learning_ = enabled; active_ = status.composing; newInput_ = false;
  if (changed) { ++revision_; pressed_ = StudyLayout::None; }
  Layout(now, changed);
  if (window_) {
    std::wstring label = L"英语学习候选";
    for (size_t i = 0; i < context_.cinfo.candies.size(); ++i) label += L"；" + AccessibleName(static_cast<int>(i));
    SetWindowTextW(window_, label.c_str());
    if (changed) {
      NotifyWinEvent(EVENT_OBJECT_REORDER, window_, OBJID_CLIENT, CHILDID_SELF);
      if (!context_.cinfo.empty()) NotifyWinEvent(EVENT_OBJECT_SELECTION, window_, OBJID_CLIENT, context_.cinfo.highlighted + 1);
    }
    if (status.composing) Paint(); else Hide();
  }
}
void CandidateUi::UpdateInputPosition(const RECT& rectangle) {
  anchor_ = rectangle;
  if (!renderEnvironment_) {
    MONITORINFO info{sizeof(info)};
    GetMonitorInfoW(MonitorFromRect(&anchor_, MONITOR_DEFAULTTONEAREST), &info);
    const UINT nextDpi = WindowDpi(window_ ? window_ : owner_);
    if (nextDpi && nextDpi != dpi_) { dpi_ = nextDpi; dirtyResources_ = true; viewportDip_ = scrollDip_ = 0; }
    const int width = MulDiv(info.rcWork.right - info.rcWork.left, 96, dpi_);
    if (width > 0 && width != workWidth_) { workWidth_ = width; viewportDip_ = scrollDip_ = 0; }
  }
  Layout(GetTickCount64()); Position();
}
void CandidateUi::Position() {
  if (!layout_) return;
  MONITORINFO info{sizeof(info)};
  if (!GetMonitorInfoW(MonitorFromRect(&anchor_, MONITOR_DEFAULTTONEAREST), &info)) return;
  const int width = layout_->GetContentSize().cx;
  const int fullHeight = MulDiv(preferences_.largeText ? 59 : 55, dpi_, 96);
  position_.x = (std::clamp)(anchor_.left, info.rcWork.left, (std::max)(info.rcWork.left, info.rcWork.right - width));
  const int below = anchor_.bottom + MulDiv(6, dpi_, 96);
  position_.y = below + fullHeight <= info.rcWork.bottom ? below : anchor_.top - fullHeight - MulDiv(6, dpi_, 96);
  position_.y = (std::max)(position_.y, info.rcWork.top);
  if (window_) SetWindowPos(window_, HWND_TOPMOST, position_.x, position_.y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE);
}
void CandidateUi::SetColor(COLORREF color, double alpha) {
  resources_->pBrush->SetColor(D2D1::ColorF(GetRValue(color) / 255.f, GetGValue(color) / 255.f,
      GetBValue(color) / 255.f, static_cast<float>(alpha)));
}
void CandidateUi::Round(const CRect& rc, COLORREF color, float radius, double alpha, bool border) {
  SetColor(color, alpha);
  const D2D1_ROUNDED_RECT shape{D2D1::RectF(static_cast<float>(rc.left), static_cast<float>(rc.top),
      static_cast<float>(rc.right), static_cast<float>(rc.bottom)), radius, radius};
  if (border) resources_->pRenderTarget->DrawRoundedRectangle(shape, resources_->pBrush.Get(), dpi_ / 96.f);
  else resources_->pRenderTarget->FillRoundedRectangle(shape, resources_->pBrush.Get());
}
void CandidateUi::Text(const std::wstring& text, const CRect& rc, IDWriteTextFormat1* format, COLORREF color, double alpha, bool wrap) {
  if (text.empty() || rc.IsRectEmpty() || !format || alpha <= 0) return;
  ComPtr<IDWriteTextLayout> layout;
  if (FAILED(resources_->pDWFactory->CreateTextLayout(text.c_str(), static_cast<UINT32>(text.size()), format,
      static_cast<float>(rc.Width()), static_cast<float>(rc.Height()), &layout))) return;
  if (wrap) layout->SetWordWrapping(DWRITE_WORD_WRAPPING_WRAP);
  SetColor(color, alpha);
  resources_->pRenderTarget->DrawTextLayout(D2D1::Point2F(static_cast<float>(rc.left), static_cast<float>(rc.top)),
      layout.Get(), resources_->pBrush.Get(), D2D1_DRAW_TEXT_OPTIONS_CLIP);
}
void CandidateUi::DrawPage(const weasel::Context& context, StudyLayout& layout, double x, double alpha, double englishAlpha) {
  if (alpha <= 0) return;
  const int dx = static_cast<int>(std::lround(x * dpi_ / 96.0));
  const auto& info = context.cinfo;
  const int count = (std::min)(static_cast<int>(info.candies.size()), weasel::MAX_CANDIDATES_COUNT);
  for (int i = 0; i < count; ++i) {
    const bool selected = i == info.highlighted;
    if (selected) Round(Shift(layout.GetCandidateRect(i), dx), style_.hilited_candidate_back_color, 10 * dpi_ / 96.f, alpha);
    const std::wstring label = i < static_cast<int>(info.labels.size()) ? info.labels[i].str : std::to_wstring(i + 1);
    Text(label, Shift(layout.GetCandidateLabelRect(i), dx), resources_->pLabelTextFormat.Get(), style_.label_text_color, alpha);
    Text(info.candies[i].str, Shift(layout.GetCandidateTextRect(i), dx), resources_->pTextFormat.Get(),
        selected ? style_.hilited_candidate_text_color : style_.candidate_text_color, alpha);
    if (i < static_cast<int>(info.comments.size())) Text(info.comments[i].str, Shift(layout.GetCandidateCommentRect(i), dx),
        resources_->pCommentTextFormat.Get(), selected ? style_.hilited_comment_text_color : style_.comment_text_color, alpha * englishAlpha);
  }
}
CandidateFrame CandidateUi::Render(std::uint64_t now) {
  Layout(now);
  if (!layout_ || !resources_->pRenderTarget) return {};
  const auto size = layout_->GetContentSize();
  Surface surface(size.cx, size.cy);
  if (!surface.previous) return {};
  RECT bounds{0, 0, size.cx, size.cy};
  auto* target = resources_->pRenderTarget.Get();
  if (FAILED(target->BindDC(surface.dc, &bounds))) return {};
  target->BeginDraw(); target->Clear(D2D1::ColorF(0, 0));
  CRect back(1, 1, size.cx - 1, size.cy - 1);
  Round(back, style_.back_color, 14 * dpi_ / 96.f);
  Round(back, style_.border_color, 14 * dpi_ / 96.f, 1, true);
  const auto view = layout_->viewport;
  target->PushAxisAlignedClip(D2D1::RectF(static_cast<float>(view.left), static_cast<float>(view.top),
      static_cast<float>(view.right), static_cast<float>(view.bottom)), D2D1_ANTIALIAS_MODE_ALIASED);
  const auto frame = motion_.At(now);
  frameWasActive_ = frame.active;
  if (!previous_.cinfo.empty() && frame.outgoingAlpha > 0) {
    StudyLayout old(style_, previous_, status_, resources_, frame.learning, viewportDip_, oldScrollDip_, preferences_.largeText);
    old.DoLayout(nullptr, resources_);
    DrawPage(previous_, old, frame.outgoingX, frame.outgoingAlpha, frame.englishAlpha);
  }
  DrawPage(context_, *layout_, frame.incomingX, frame.incomingAlpha, frame.englishAlpha);
  target->PopAxisAlignedClip();
  const float sep = static_cast<float>(view.right) + 4 * dpi_ / 96.f;
  SetColor(style_.border_color);
  target->DrawLine(D2D1::Point2F(sep, 10 * dpi_ / 96.f), D2D1::Point2F(sep, size.cy - 10 * dpi_ / 96.f), resources_->pBrush.Get());
  const wchar_t* labels[] = {L"‹", L"›", learning_ ? L"学" : L"关", L"⋯"};
  for (int i = 0; i < 4; ++i) {
    const int hit = StudyLayout::Previous - i;
    const auto rc = layout_->tools[i];
    if (hover_ == hit && Enabled(hit)) Round(rc, style_.hilited_candidate_back_color, 6 * dpi_ / 96.f);
    CRect text = rc; text.left += MulDiv(i == 2 ? 4 : 7, dpi_, 96); text.top += MulDiv(3, dpi_, 96);
    Text(labels[i], text, resources_->pLabelTextFormat.Get(), i == 2 && learning_ ? style_.hilited_comment_text_color : style_.label_text_color,
        Enabled(hit) ? 1 : .35);
  }
  if (FAILED(target->EndDraw())) { dirtyResources_ = true; return {}; }
  return surface.Copy();
}
void CandidateUi::Paint() {
  if (!window_) return;
  const auto frame = Render(GetTickCount64());
  if (frameObserver) frameObserver(false, frame);
  Position(); Display(window_, frame, position_);
}
bool CandidateUi::Enabled(int hit) const {
  if (!snapshotCurrent_ || !status_.composing || context_.cinfo.empty()) return false;
  if (hit >= 0) return hit < static_cast<int>(context_.cinfo.candies.size());
  if (hit == StudyLayout::Previous) return context_.cinfo.currentPage > 0;
  if (hit == StudyLayout::Next) return !context_.cinfo.is_last_page;
  return capable_ && (hit == StudyLayout::Learning || hit == StudyLayout::More);
}
CRect CandidateUi::HitRectangle(int hit) const {
  if (!layout_) return {};
  if (hit >= 0 && hit < static_cast<int>(context_.cinfo.candies.size())) return layout_->GetCandidateRect(hit);
  if (hit <= StudyLayout::Previous && hit >= StudyLayout::More) return layout_->tools[StudyLayout::Previous - hit];
  return {};
}
std::wstring CandidateUi::AccessibleName(int hit) const {
  if (hit >= 0 && hit < static_cast<int>(context_.cinfo.candies.size())) {
    auto name = std::to_wstring(hit + 1) + L" " + context_.cinfo.candies[hit].str;
    if (learning_ && capable_ && hit < static_cast<int>(context_.cinfo.comments.size()) && !context_.cinfo.comments[hit].str.empty())
      name += L"，" + context_.cinfo.comments[hit].str;
    return name;
  }
  if (hit == StudyLayout::Previous) return L"上一页";
  if (hit == StudyLayout::Next) return L"下一页";
  if (hit == StudyLayout::Learning) return learning_ ? L"关闭学习模式" : L"开启学习模式";
  if (hit == StudyLayout::More) return L"更多候选操作";
  return {};
}
POINT CandidateUi::MenuPosition(unsigned index) const {
  const auto rc = HitRectangle(static_cast<int>(index));
  return {position_.x + rc.left, position_.y + (layout_ ? layout_->GetContentSize().cy : 0) + MulDiv(5, dpi_, 96)};
}
void CandidateUi::Invoke(int hit) {
  if (!Enabled(hit)) return;
  motion_.CancelPage(); previous_ = {}; HideDefinition();
  if (hit >= 0) {
    auto callback = callback_; size_t index = static_cast<size_t>(hit);
    if (callback) callback(&index, nullptr, nullptr, nullptr);
  } else if (hit == StudyLayout::Previous || hit == StudyLayout::Next) {
    auto callback = callback_; bool next = hit == StudyLayout::Next;
    if (callback) callback(nullptr, nullptr, &next, nullptr);
  } else if (hit == StudyLayout::Learning) {
    auto callback = studyLearning;
    if (callback) callback(!learning_);
  } else if (hit == StudyLayout::More) {
    auto callback = studyMenu; const unsigned index = static_cast<unsigned>(context_.cinfo.highlighted);
    if (callback) callback(index, owner_, MenuPosition(index));
  }
}
void CandidateUi::ShowDefinition(const ActionState& target, unsigned index, bool pinned) {
  if (!capable_ || !learning_ || !target.learning || index >= context_.cinfo.candies.size() || !window_) return;
  HideDefinition(); definition_ = target; detailPinned_ = pinned; detailScroll_ = 0;
  WNDCLASSW cls{}; cls.hInstance = Module(); cls.lpszClassName = DefinitionClass;
  cls.lpfnWndProc = DetailProc; cls.hCursor = LoadCursor(nullptr, IDC_ARROW);
  if (!RegisterClassW(&cls) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) return;
  const auto label = Wide(target.chinese) + L"；" + Wide(target.english);
  detail_ = CreateWindowExW(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_LAYERED,
      DefinitionClass, label.c_str(), WS_POPUP, 0, 0, 1, 1, window_, nullptr, cls.hInstance, this);
  PaintDefinition(); ShowWindow(detail_, SW_SHOWNOACTIVATE);
}
void CandidateUi::HideDefinition() {
  if (detail_) DestroyWindow(detail_);
  detail_ = nullptr; definition_ = {}; detailScroll_ = 0; detailPinned_ = false;
}
bool CandidateUi::DefinitionVisible() const { return detail_ && IsWindowVisible(detail_); }
CandidateFrame CandidateUi::RenderDefinition() {
  ConfigureResources();
  if (!resources_ || !resources_->pRenderTarget) return {};
  const float scale = dpi_ / 96.f;
  const int width = static_cast<int>((std::min)(300, workWidth_ - 24) * scale);
  ComPtr<IDWriteTextFormat> base; ComPtr<IDWriteTextFormat1> format;
  resources_->pDWFactory->CreateTextFormat(L"Segoe UI", nullptr, DWRITE_FONT_WEIGHT_NORMAL,
      DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_STRETCH_NORMAL, 15 * scale, L"zh-CN", &base);
  if (!base) return {};
  base->SetLineSpacing(DWRITE_LINE_SPACING_METHOD_UNIFORM, 22 * scale, 17 * scale);
  base.As(&format);
  const auto english = definition_.english.empty() ? L"暂无可靠释义" : Wide(definition_.english);
  ComPtr<IDWriteTextLayout> text;
  resources_->pDWFactory->CreateTextLayout(english.c_str(), static_cast<UINT32>(english.size()), base.Get(),
      width - 24 * scale, 20000, &text);
  DWRITE_TEXT_METRICS metrics{};
  if (text) text->GetMetrics(&metrics);
  detailContentHeight_ = static_cast<int>(std::ceil(metrics.height));
  MONITORINFO monitor{sizeof(monitor)}; GetMonitorInfoW(MonitorFromRect(&anchor_, MONITOR_DEFAULTTONEAREST), &monitor);
  const int maxHeight = (std::max)(static_cast<int>(120 * scale), static_cast<int>(monitor.rcWork.bottom - monitor.rcWork.top) - static_cast<int>(40 * scale));
  const int height = (std::min)(static_cast<int>(80 * scale) + detailContentHeight_, maxHeight);
  const int contentHeight = height - static_cast<int>(80 * scale);
  detailScroll_ = (std::clamp)(detailScroll_, 0, (std::max)(0, detailContentHeight_ - contentHeight));
  Surface surface(width, height); if (!surface.previous) return {};
  RECT bounds{0, 0, width, height}; auto* rt = resources_->pRenderTarget.Get();
  if (FAILED(rt->BindDC(surface.dc, &bounds))) return {};
  rt->BeginDraw(); rt->Clear(D2D1::ColorF(0, 0));
  Round(CRect(1, 1, width - 1, height - 1), style_.back_color, 12 * scale);
  Round(CRect(1, 1, width - 1, height - 1), style_.border_color, 12 * scale, 1, true);
  Text(Wide(definition_.chinese) + L" · 完整释义", CRect(static_cast<int>(12 * scale), static_cast<int>(10 * scale), width - static_cast<int>(38 * scale), static_cast<int>(32 * scale)),
      resources_->pCommentTextFormat.Get(), style_.comment_text_color);
  Text(L"×", CRect(width - static_cast<int>(28 * scale), static_cast<int>(7 * scale), width - static_cast<int>(6 * scale), static_cast<int>(32 * scale)),
      resources_->pLabelTextFormat.Get(), style_.label_text_color);
  rt->PushAxisAlignedClip(D2D1::RectF(12 * scale, 38 * scale, width - 12 * scale, height - 42 * scale), D2D1_ANTIALIAS_MODE_ALIASED);
  Text(english, CRect(static_cast<int>(12 * scale), static_cast<int>(38 * scale) - detailScroll_, width - static_cast<int>(12 * scale),
      static_cast<int>(38 * scale) - detailScroll_ + detailContentHeight_ + 2), format.Get(), style_.hilited_comment_text_color, 1, true);
  rt->PopAxisAlignedClip();
  const wchar_t* note = definition_.reason == "partial-composition" ? L"请先完成整段拼音，再输入英文。" : L"示例常用义 · 不做上下文翻译";
  Text(note, CRect(static_cast<int>(12 * scale), height - static_cast<int>(32 * scale), width - static_cast<int>(12 * scale), height - static_cast<int>(8 * scale)),
      resources_->pCommentTextFormat.Get(), style_.comment_text_color);
  if (FAILED(rt->EndDraw())) return {};
  return surface.Copy();
}
void CandidateUi::PaintDefinition() {
  if (!detail_) return;
  const auto frame = RenderDefinition();
  if (frameObserver) frameObserver(true, frame);
  POINT at = MenuPosition(definition_.index);
  MONITORINFO info{sizeof(info)}; GetMonitorInfoW(MonitorFromRect(&anchor_, MONITOR_DEFAULTTONEAREST), &info);
  at.x = (std::clamp)(at.x, info.rcWork.left, (std::max)(info.rcWork.left, info.rcWork.right - frame.width));
  if (at.y + frame.height > info.rcWork.bottom) at.y = (std::max)(info.rcWork.top, position_.y - frame.height - MulDiv(5, dpi_, 96));
  Display(detail_, frame, at);
}
LRESULT CALLBACK CandidateUi::WindowProc(HWND window, UINT message, WPARAM wp, LPARAM lp) {
  auto* ui = reinterpret_cast<CandidateUi*>(GetWindowLongPtrW(window, GWLP_USERDATA));
  if (message == WM_NCCREATE) {
    ui = static_cast<CandidateUi*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
    ui->window_ = window; SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(ui));
  }
  if (!ui) return DefWindowProcW(window, message, wp, lp);
  switch (message) {
    case WM_GETOBJECT:
      if (static_cast<LONG>(lp) == OBJID_CLIENT) {
        auto* accessible = CreateCandidateAccessible(window, ui->access_, ui->accessibilityLifetime);
        if (!accessible) return 0;
        const auto result = LresultFromObject(IID_IAccessible, wp, accessible);
        accessible->Release(); return result;
      }
      break;
    case WM_MOUSEACTIVATE: return MA_NOACTIVATE;
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
      PAINTSTRUCT ps; BeginPaint(window, &ps); EndPaint(window, &ps); ui->Paint(); return 0;
    }
    case WM_SETTINGCHANGE:
    case WM_THEMECHANGED: ui->dirtyResources_ = true; ui->motion_.Finish(); ui->Paint(); return 0;
    case WM_DPICHANGED: ui->dpi_ = HIWORD(wp); ui->dirtyResources_ = true; ui->viewportDip_ = 0; ui->Paint(); return 0;
    case WM_LBUTTONDOWN: {
      if (!ui->layout_) return 0;
      ui->pressed_ = ui->layout_->Hit(POINT{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)});
      ui->pressedRevision_ = ui->revision_; SetCapture(window); return 0;
    }
    case WM_LBUTTONUP: {
      const int hit = ui->layout_ ? ui->layout_->Hit(POINT{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)}) : StudyLayout::None;
      const bool matched = hit == ui->pressed_ && ui->pressedRevision_ == ui->revision_;
      ui->pressed_ = StudyLayout::None;
      if (GetCapture() == window) ReleaseCapture();
      if (matched) ui->Invoke(hit);
      return 0;
    }
    case WM_CAPTURECHANGED: ui->pressed_ = StudyLayout::None; return 0;
    case WM_CONTEXTMENU: {
      POINT point{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)};
      int hit = ui->context_.cinfo.highlighted;
      if (point.x != -1 || point.y != -1) {
        ScreenToClient(window, &point); hit = ui->layout_ ? ui->layout_->Hit(point) : StudyLayout::None;
      }
      if (hit >= 0 && ui->Enabled(hit)) {
        auto callback = ui->studyMenu; const auto at = ui->MenuPosition(static_cast<unsigned>(hit));
        if (callback) callback(static_cast<unsigned>(hit), ui->owner_, at);
      }
      return 0;
    }
    case WM_MOUSEMOVE: {
      TRACKMOUSEEVENT track{sizeof(track), TME_LEAVE, window, 0}; TrackMouseEvent(&track); ui->pointerInside_ = true;
      const int hit = ui->layout_ ? ui->layout_->Hit(POINT{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)}) : StudyLayout::None;
      if (hit != ui->hover_) { ui->hover_ = hit; ui->hoverStart_ = GetTickCount64(); if (!ui->detailPinned_) ui->HideDefinition(); ui->Paint(); }
      return 0;
    }
    case WM_MOUSELEAVE: ui->pointerInside_ = false; ui->hover_ = StudyLayout::None; ui->Paint(); return 0;
    case WM_MOUSEWHEEL: {
      if (ui->layout_ && ui->layout_->naturalWidthDip > ui->viewportDip_) {
        ui->scrollDip_ += GET_WHEEL_DELTA_WPARAM(wp) < 0 ? 96 : -96;
        ui->motion_.CancelPage(); ui->HideDefinition(); ui->Paint();
      } else ui->Invoke(GET_WHEEL_DELTA_WPARAM(wp) < 0 ? StudyLayout::Next : StudyLayout::Previous);
      return 0;
    }
    case WM_TIMER: {
      const auto now = GetTickCount64();
      if (now - ui->lastPoll_ >= 250) {
        ui->lastPoll_ = now;
        auto poll = ui->studyPoll;
        if (poll && !poll()) return 0;
        if (ui->detail_ && !ui->detailPinned_) {
          POINT cursor{}; GetCursorPos(&cursor); RECT region{}; GetWindowRect(ui->detail_, &region);
          InflateRect(&region, MulDiv(6, ui->dpi_, 96), MulDiv(6, ui->dpi_, 96));
          if (!ui->pointerInside_ && !PtInRect(&region, cursor)) ui->HideDefinition();
        }
      }
      if (ui->motion_.At(now).active || ui->frameWasActive_) ui->Paint();
      else if (!ui->previous_.cinfo.empty()) { ui->previous_ = {}; ui->Paint(); }
      if (ui->hover_ >= 0 && ui->learning_ && ui->capable_ && !ui->detail_ && ui->hoverStart_ && now - ui->hoverStart_ >= 450) {
        const auto index = static_cast<unsigned>(ui->hover_); auto callback = ui->studyDetail; ui->hoverStart_ = 0;
        if (callback) callback(index, false);
      }
      return 0;
    }
    case WM_NCDESTROY:
      KillTimer(window, 1); ui->window_ = nullptr;
      if (ui->access_) ui->access_->view = nullptr;
      SetWindowLongPtrW(window, GWLP_USERDATA, 0); return DefWindowProcW(window, message, wp, lp);
  }
  return DefWindowProcW(window, message, wp, lp);
}
LRESULT CALLBACK CandidateUi::DetailProc(HWND window, UINT message, WPARAM wp, LPARAM lp) {
  auto* ui = reinterpret_cast<CandidateUi*>(GetWindowLongPtrW(window, GWLP_USERDATA));
  if (message == WM_NCCREATE) {
    ui = static_cast<CandidateUi*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
    ui->detail_ = window; SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(ui));
  }
  if (!ui) return DefWindowProcW(window, message, wp, lp);
  if (message == WM_MOUSEACTIVATE) return MA_NOACTIVATE;
  if (message == WM_LBUTTONUP) {
    RECT rc{}; GetClientRect(window, &rc);
    if (GET_X_LPARAM(lp) > rc.right - MulDiv(36, ui->dpi_, 96) && GET_Y_LPARAM(lp) < MulDiv(36, ui->dpi_, 96)) ui->HideDefinition();
    return 0;
  }
  if (message == WM_MOUSEWHEEL) {
    ui->detailScroll_ += GET_WHEEL_DELTA_WPARAM(wp) < 0 ? MulDiv(44, ui->dpi_, 96) : -MulDiv(44, ui->dpi_, 96);
    ui->PaintDefinition(); return 0;
  }
  if (message == WM_PAINT) { PAINTSTRUCT ps; BeginPaint(window, &ps); EndPaint(window, &ps); ui->PaintDefinition(); return 0; }
  if (message == WM_NCDESTROY) { ui->detail_ = nullptr; SetWindowLongPtrW(window, GWLP_USERDATA, 0); }
  return DefWindowProcW(window, message, wp, lp);
}
}

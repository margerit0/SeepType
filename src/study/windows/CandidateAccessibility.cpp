#include "stdafx.h"
#include "CandidateAccessibility.h"
#include "CandidateUi.h"

namespace study {
namespace {
class CandidateAccessible final : public IAccessible {
 public:
  CandidateAccessible(HWND window, std::shared_ptr<CandidateAccessBinding> binding, std::function<void(bool)> lifetime)
      : window_(window), binding_(std::move(binding)), lifetime_(std::move(lifetime)) { if (lifetime_) lifetime_(true); }
  ~CandidateAccessible() { if (lifetime_) lifetime_(false); }
  STDMETHODIMP QueryInterface(REFIID id, void** out) override {
    if (!out) return E_POINTER;
    *out = nullptr;
    if (id != IID_IUnknown && id != IID_IDispatch && id != IID_IAccessible) return E_NOINTERFACE;
    *out = static_cast<IAccessible*>(this); AddRef(); return S_OK;
  }
  STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&refs_); }
  STDMETHODIMP_(ULONG) Release() override { const auto n = InterlockedDecrement(&refs_); if (!n) delete this; return n; }
  STDMETHODIMP GetTypeInfoCount(UINT* count) override { if (!count) return E_POINTER; *count = 0; return S_OK; }
  STDMETHODIMP GetTypeInfo(UINT, LCID, ITypeInfo** out) override { if (out) *out = nullptr; return E_NOTIMPL; }
  STDMETHODIMP GetIDsOfNames(REFIID, LPOLESTR*, UINT, LCID, DISPID*) override { return DISP_E_UNKNOWNNAME; }
  STDMETHODIMP Invoke(DISPID, REFIID, LCID, WORD, DISPPARAMS*, VARIANT*, EXCEPINFO*, UINT*) override { return DISP_E_MEMBERNOTFOUND; }
  CandidateUi* View() const {
    auto* view = binding_ ? binding_->view : nullptr;
    return view && view->Window() == window_ && view->IsShown() ? view : nullptr;
  }
  LONG Candidates() const { auto* view = View(); return view ? static_cast<LONG>(view->ctx().cinfo.candies.size()) : 0; }
  LONG Count() const { return View() ? Candidates() + 4 : 0; }
  bool Child(VARIANT child) const { return child.vt == VT_I4 && child.lVal >= 0 && child.lVal <= Count(); }
  int Hit(LONG child) const { return child <= Candidates() ? static_cast<int>(child - 1) : StudyLayout::Previous - static_cast<int>(child - Candidates() - 1); }
  STDMETHODIMP get_accParent(IDispatch** out) override {
    if (!out) return E_POINTER; *out = nullptr;
    if (!View()) return S_FALSE;
    return AccessibleObjectFromWindow(window_, OBJID_WINDOW, IID_IDispatch, reinterpret_cast<void**>(out));
  }
  STDMETHODIMP get_accChildCount(LONG* out) override { if (!out) return E_POINTER; *out = Count(); return S_OK; }
  STDMETHODIMP get_accChild(VARIANT child, IDispatch** out) override {
    if (!out) return E_POINTER; *out = nullptr; return Child(child) ? S_FALSE : E_INVALIDARG;
  }
  STDMETHODIMP get_accName(VARIANT child, BSTR* out) override {
    if (!out) return E_POINTER; *out = nullptr;
    if (!Child(child) || !View()) return E_INVALIDARG;
    const auto name = child.lVal == CHILDID_SELF ? std::wstring(L"英语学习候选") : View()->AccessibleName(Hit(child.lVal));
    *out = SysAllocStringLen(name.data(), static_cast<UINT>(name.size())); return *out ? S_OK : E_OUTOFMEMORY;
  }
  STDMETHODIMP get_accValue(VARIANT, BSTR* out) override { if (!out) return E_POINTER; *out = nullptr; return S_FALSE; }
  STDMETHODIMP get_accDescription(VARIANT child, BSTR* out) override {
    if (!out) return E_POINTER; *out = nullptr;
    if (!Child(child)) return E_INVALIDARG;
    if (child.lVal > 0 && child.lVal <= Candidates()) *out = SysAllocString(L"普通操作输入中文；F2 查看释义，右键选择输入英文。");
    return *out ? S_OK : S_FALSE;
  }
  STDMETHODIMP get_accRole(VARIANT child, VARIANT* out) override {
    if (!out) return E_POINTER; VariantInit(out);
    if (!Child(child)) return E_INVALIDARG;
    out->vt = VT_I4; out->lVal = child.lVal == 0 ? ROLE_SYSTEM_LIST : child.lVal <= Candidates() ? ROLE_SYSTEM_LISTITEM : ROLE_SYSTEM_PUSHBUTTON;
    return S_OK;
  }
  STDMETHODIMP get_accState(VARIANT child, VARIANT* out) override {
    if (!out) return E_POINTER; VariantInit(out);
    if (!Child(child)) return E_INVALIDARG;
    out->vt = VT_I4;
    auto* view = View();
    if (!view) { out->lVal = STATE_SYSTEM_UNAVAILABLE | STATE_SYSTEM_INVISIBLE; return S_OK; }
    if (child.lVal) {
      const int hit = Hit(child.lVal);
      if (!view->Enabled(hit)) out->lVal |= STATE_SYSTEM_UNAVAILABLE;
      if (hit >= 0) {
        out->lVal |= STATE_SYSTEM_SELECTABLE;
        if (hit == view->ctx().cinfo.highlighted) out->lVal |= STATE_SYSTEM_SELECTED;
        auto rectangle = view->HitRectangle(hit); CRect clipped;
        if (!view->Geometry() || !clipped.IntersectRect(rectangle, view->Geometry()->viewport)) out->lVal |= STATE_SYSTEM_OFFSCREEN;
      }
    }
    return S_OK;
  }
  STDMETHODIMP get_accHelp(VARIANT, BSTR* out) override { if (!out) return E_POINTER; *out = nullptr; return S_FALSE; }
  STDMETHODIMP get_accHelpTopic(BSTR* file, VARIANT, LONG* topic) override {
    if (!file || !topic) return E_POINTER; *file = nullptr; *topic = 0; return S_FALSE;
  }
  STDMETHODIMP get_accKeyboardShortcut(VARIANT child, BSTR* out) override {
    if (!out) return E_POINTER; *out = nullptr;
    if (!Child(child) || !child.lVal) return S_FALSE;
    const int hit = Hit(child.lVal);
    const wchar_t* key = hit == StudyLayout::Previous ? L"PageUp" : hit == StudyLayout::Next ? L"PageDown" : hit == StudyLayout::More ? L"Shift+F10" : nullptr;
    if (key) *out = SysAllocString(key); return *out ? S_OK : S_FALSE;
  }
  STDMETHODIMP get_accFocus(VARIANT* out) override { if (!out) return E_POINTER; VariantInit(out); return S_FALSE; }
  STDMETHODIMP get_accSelection(VARIANT* out) override {
    if (!out) return E_POINTER; VariantInit(out);
    auto* view = View(); if (!view || !Candidates()) return S_FALSE;
    out->vt = VT_I4; out->lVal = view->ctx().cinfo.highlighted + 1; return S_OK;
  }
  STDMETHODIMP get_accDefaultAction(VARIANT child, BSTR* out) override {
    if (!out) return E_POINTER; *out = nullptr;
    if (!Child(child) || !child.lVal) return E_INVALIDARG;
    *out = SysAllocString(child.lVal <= Candidates() ? L"输入中文" : L"按下"); return *out ? S_OK : E_OUTOFMEMORY;
  }
  STDMETHODIMP accSelect(LONG flags, VARIANT child) override {
    auto* view = View();
    if (!view || !Child(child) || child.lVal < 1 || child.lVal > Candidates() || !(flags & SELFLAG_TAKESELECTION)) return E_INVALIDARG;
    size_t index = static_cast<size_t>(child.lVal - 1);
    auto callback = view->uiCallback();
    if (!view->Enabled(static_cast<int>(index)) || !callback) return E_ACCESSDENIED;
    callback(nullptr, &index, nullptr, nullptr); return S_OK;
  }
  STDMETHODIMP accLocation(LONG* x, LONG* y, LONG* width, LONG* height, VARIANT child) override {
    if (!x || !y || !width || !height) return E_POINTER;
    *x = *y = *width = *height = 0;
    auto* view = View(); if (!view || !Child(child)) return E_INVALIDARG;
    CRect rectangle;
    if (!child.lVal) GetClientRect(window_, &rectangle);
    else {
      rectangle = view->HitRectangle(Hit(child.lVal));
      if (child.lVal <= Candidates() && view->Geometry()) rectangle.IntersectRect(rectangle, view->Geometry()->viewport);
    }
    POINT point{rectangle.left, rectangle.top}; ClientToScreen(window_, &point);
    *x = point.x; *y = point.y; *width = rectangle.Width(); *height = rectangle.Height(); return S_OK;
  }
  STDMETHODIMP accNavigate(LONG direction, VARIANT start, VARIANT* out) override {
    if (!out) return E_POINTER; VariantInit(out);
    if (!Child(start)) return E_INVALIDARG;
    LONG next = 0;
    if (direction == NAVDIR_FIRSTCHILD && !start.lVal) next = 1;
    if (direction == NAVDIR_LASTCHILD && !start.lVal) next = Count();
    if (direction == NAVDIR_NEXT && start.lVal) next = start.lVal + 1;
    if (direction == NAVDIR_PREVIOUS && start.lVal) next = start.lVal - 1;
    if (next < 1 || next > Count()) return S_FALSE;
    out->vt = VT_I4; out->lVal = next; return S_OK;
  }
  STDMETHODIMP accHitTest(LONG x, LONG y, VARIANT* out) override {
    if (!out) return E_POINTER; VariantInit(out);
    auto* view = View(); if (!view || !view->Geometry()) return S_FALSE;
    POINT point{x, y}; ScreenToClient(window_, &point);
    RECT bounds{}; GetClientRect(window_, &bounds); if (!PtInRect(&bounds, point)) return S_FALSE;
    const int hit = view->Geometry()->Hit(point);
    out->vt = VT_I4;
    out->lVal = hit >= 0 ? hit + 1 : hit <= StudyLayout::Previous && hit >= StudyLayout::More ? Candidates() + 1 + StudyLayout::Previous - hit : CHILDID_SELF;
    return S_OK;
  }
  STDMETHODIMP accDoDefaultAction(VARIANT child) override {
    auto* view = View();
    if (!view || !Child(child) || !child.lVal) return E_INVALIDARG;
    const int hit = Hit(child.lVal);
    if (!view->Enabled(hit)) return E_ACCESSDENIED;
    view->Invoke(hit); return S_OK;
  }
  STDMETHODIMP put_accName(VARIANT, BSTR) override { return E_NOTIMPL; }
  STDMETHODIMP put_accValue(VARIANT, BSTR) override { return E_NOTIMPL; }
 private:
  LONG refs_ = 1;
  HWND window_;
  std::shared_ptr<CandidateAccessBinding> binding_;
  std::function<void(bool)> lifetime_;
};
}
IAccessible* CreateCandidateAccessible(HWND window, std::shared_ptr<CandidateAccessBinding> binding, std::function<void(bool)> lifetime) {
  return new CandidateAccessible(window, std::move(binding), std::move(lifetime));
}
}

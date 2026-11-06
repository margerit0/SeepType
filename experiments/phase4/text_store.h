// Minimal plain-text application store. All ranges, edit cookies, composition
// and edit-session scheduling are supplied by Windows msctf, not mocked here.
#pragma once
#include <windows.h>
#include <textstor.h>
#include <msctf.h>
#include <atlbase.h>
#include <algorithm>
#include <string>
#include <vector>

class TextStore : public ITextStoreACP, public ITfContextOwnerCompositionSink {
 public:
  HWND window = nullptr;
  std::wstring text;
  std::vector<std::wstring> writes;
  bool defer = false;
  DWORD lock = 0, pending = 0;
  unsigned syncGrants = 0, asyncGrants = 0, violations = 0, compositions = 0;
  HRESULT lastGrant = S_OK;
  TS_SELECTION_ACP selection{0, 0, {TS_AE_END, FALSE}};
  CComPtr<ITextStoreACPSink> sink;
  ULONG refs = 1;

  STDMETHODIMP QueryInterface(REFIID id, void** out) override {
    if (!out) return E_POINTER;
    *out = nullptr;
    if (id == IID_IUnknown || id == IID_ITextStoreACP) *out = static_cast<ITextStoreACP*>(this);
    if (id == IID_ITfContextOwnerCompositionSink) *out = static_cast<ITfContextOwnerCompositionSink*>(this);
    if (!*out) return E_NOINTERFACE;
    AddRef(); return S_OK;
  }
  STDMETHODIMP_(ULONG) AddRef() override { return ++refs; }
  STDMETHODIMP_(ULONG) Release() override { auto n = --refs; if (!n) delete this; return n; }
  STDMETHODIMP AdviseSink(REFIID id, IUnknown* value, DWORD) override {
    if (id != IID_ITextStoreACPSink || !value) return E_INVALIDARG;
    if (sink) return CONNECT_E_ADVISELIMIT;
    return value->QueryInterface(&sink);
  }
  STDMETHODIMP UnadviseSink(IUnknown* value) override {
    CComPtr<IUnknown> a, b;
    if (!sink || !value) return CONNECT_E_NOCONNECTION;
    sink->QueryInterface(&a); value->QueryInterface(&b);
    if (a != b) return CONNECT_E_NOCONNECTION;
    sink.Release(); pending = 0; return S_OK;
  }
  HRESULT Grant(DWORD flags) {
    lock = flags & TS_LF_READWRITE;
    lastGrant = sink->OnLockGranted(flags);
    lock = 0;
    InvalidateRect(window, nullptr, TRUE);
    return lastGrant;
  }
  STDMETHODIMP RequestLock(DWORD flags, HRESULT* result) override {
    if (!result || !sink) return E_INVALIDARG;
    if (lock || defer) {
      if (flags & TS_LF_SYNC) *result = TS_E_SYNCHRONOUS;
      else { pending |= flags & TS_LF_READWRITE; *result = TS_S_ASYNC; }
    } else { ++syncGrants; *result = Grant(flags); }
    return S_OK;
  }
  void Drain() {
    defer = false;
    for (unsigned n = 0; pending && n < 100; ++n) {
      auto flags = pending; pending = 0; ++asyncGrants; Grant(flags);
    }
  }
  bool Locked(bool write = false) {
    bool ok = write ? (lock & TS_LF_READWRITE) == TS_LF_READWRITE : (lock & TS_LF_READ) != 0;
    if (!ok) ++violations;
    return ok;
  }
  bool Range(LONG a, LONG b) const { return a >= 0 && b >= a && b <= static_cast<LONG>(text.size()); }
  STDMETHODIMP GetStatus(TS_STATUS* out) override { if (!out) return E_POINTER; *out = {0, TS_SS_NOHIDDENTEXT}; return S_OK; }
  STDMETHODIMP QueryInsert(LONG a, LONG b, ULONG, LONG* start, LONG* end) override {
    if (!start || !end || !Range(a,b)) return E_INVALIDARG;
    *start=a; *end=b; return S_OK;
  }
  STDMETHODIMP GetSelection(ULONG index, ULONG count, TS_SELECTION_ACP* out, ULONG* got) override {
    if (!Locked()) return TS_E_NOLOCK;
    if (!out || !got || !count || (index != 0 && index != TS_DEFAULT_SELECTION)) return E_INVALIDARG;
    *out = selection; *got=1; return S_OK;
  }
  STDMETHODIMP SetSelection(ULONG count, const TS_SELECTION_ACP* value) override {
    if (!Locked(true)) return TS_E_NOLOCK;
    if (count != 1 || !value || !Range(value->acpStart,value->acpEnd)) return E_INVALIDARG;
    selection=*value; return S_OK;
  }
  STDMETHODIMP GetText(LONG a, LONG b, WCHAR* out, ULONG capacity, ULONG* got,
      TS_RUNINFO* runs, ULONG runCapacity, ULONG* runCount, LONG* next) override {
    if (!Locked()) return TS_E_NOLOCK;
    if (b == -1) b=static_cast<LONG>(text.size());
    if (!Range(a,b) || !got || !runCount || !next) return E_INVALIDARG;
    ULONG n=std::min<ULONG>(b-a,capacity);
    if (n && !out) return E_INVALIDARG;
    if (n) std::copy_n(text.data()+a,n,out);
    // A runs-only query must advance even without a text buffer.
    ULONG covered = capacity ? n : (runCapacity ? b-a : 0);
    *got=n; *runCount=covered && runCapacity ? 1 : 0;
    if (*runCount) { if (!runs) return E_INVALIDARG; runs[0]={covered,TS_RT_PLAIN}; }
    *next=a+covered; return S_OK;
  }
  STDMETHODIMP SetText(DWORD, LONG a, LONG b, const WCHAR* value, ULONG count, TS_TEXTCHANGE* change) override {
    if (!Locked(true)) return TS_E_NOLOCK;
    if (!Range(a,b) || (!value && count) || !change) return E_INVALIDARG;
    std::wstring insert = count ? std::wstring(value,count) : L"";
    text.replace(a,b-a,insert); writes.push_back(insert);
    *change={a,b,a+static_cast<LONG>(count)};
    selection={change->acpNewEnd,change->acpNewEnd,{TS_AE_END,FALSE}};
    return S_OK;
  }
  STDMETHODIMP InsertTextAtSelection(DWORD flags, const WCHAR* value, ULONG count, LONG* a, LONG* b, TS_TEXTCHANGE* change) override {
    if (!Locked(!(flags & TS_IAS_QUERYONLY))) return TS_E_NOLOCK;
    LONG start=selection.acpStart, end=selection.acpEnd;
    if (a) *a=start;
    if (b) *b=end;
    if (flags & TS_IAS_QUERYONLY) return S_OK;
    HRESULT hr=SetText(0,start,end,value,count,change);
    if (SUCCEEDED(hr) && b) *b=start+count;
    return hr;
  }
  STDMETHODIMP GetFormattedText(LONG,LONG,IDataObject** out) override { if(out)*out=nullptr; return E_NOTIMPL; }
  STDMETHODIMP GetEmbedded(LONG,REFGUID,REFIID,IUnknown** out) override { if(out)*out=nullptr; return E_NOTIMPL; }
  STDMETHODIMP QueryInsertEmbedded(const GUID*,const FORMATETC*,BOOL* out) override { if(!out)return E_POINTER; *out=FALSE; return S_OK; }
  STDMETHODIMP InsertEmbedded(DWORD,LONG,LONG,IDataObject*,TS_TEXTCHANGE*) override { return E_NOTIMPL; }
  STDMETHODIMP InsertEmbeddedAtSelection(DWORD,IDataObject*,LONG*,LONG*,TS_TEXTCHANGE*) override { return E_NOTIMPL; }
  STDMETHODIMP RequestSupportedAttrs(DWORD,ULONG,const TS_ATTRID*) override { return S_OK; }
  STDMETHODIMP RequestAttrsAtPosition(LONG,ULONG,const TS_ATTRID*,DWORD) override { return S_OK; }
  STDMETHODIMP RequestAttrsTransitioningAtPosition(LONG,ULONG,const TS_ATTRID*,DWORD) override { return S_OK; }
  STDMETHODIMP FindNextAttrTransition(LONG,LONG halt,ULONG,const TS_ATTRID*,DWORD,LONG* next,BOOL* found,LONG* offset) override {
    if (!next || !found || !offset) return E_POINTER;
    *next=halt; *found=FALSE; *offset=0; return S_OK;
  }
  STDMETHODIMP RetrieveRequestedAttrs(ULONG,TS_ATTRVAL*,ULONG* got) override { if(!got)return E_POINTER; *got=0; return S_OK; }
  STDMETHODIMP GetEndACP(LONG* out) override { if(!Locked())return TS_E_NOLOCK; if(!out)return E_POINTER; *out=static_cast<LONG>(text.size()); return S_OK; }
  STDMETHODIMP GetActiveView(TsViewCookie* out) override { if(!out)return E_POINTER; *out=1; return S_OK; }
  STDMETHODIMP GetACPFromPoint(TsViewCookie,const POINT*,DWORD,LONG*) override { return E_NOTIMPL; }
  STDMETHODIMP GetTextExt(TsViewCookie,LONG a,LONG b,RECT* out,BOOL* clipped) override {
    if(!Locked())return TS_E_NOLOCK;
    if(!Range(a,b) || !out || !clipped)return E_INVALIDARG;
    POINT point{16+static_cast<LONG>(a*14),40}; ClientToScreen(window,&point);
    *out={point.x,point.y,point.x+std::max<LONG>(2,(b-a)*14),point.y+28}; *clipped=FALSE; return S_OK;
  }
  STDMETHODIMP GetScreenExt(TsViewCookie,RECT* out) override { if(!out)return E_POINTER; GetWindowRect(window,out); return S_OK; }
  STDMETHODIMP GetWnd(TsViewCookie,HWND* out) override { if(!out)return E_POINTER; *out=window; return S_OK; }
  STDMETHODIMP OnStartComposition(ITfCompositionView*,BOOL* accept) override { *accept=TRUE; ++compositions; return S_OK; }
  STDMETHODIMP OnUpdateComposition(ITfCompositionView*,ITfRange*) override { return S_OK; }
  STDMETHODIMP OnEndComposition(ITfCompositionView*) override { if(compositions)--compositions; return S_OK; }
};

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "text_store.h"
#include <WeaselIPC.h>
#include <imm.h>
#include <oleacc.h>
#include <study/windows/UiPreferences.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <functional>

static void Require(HRESULT hr, const char* what) {
  if (FAILED(hr)) { std::cerr << what << " HRESULT=" << std::hex << hr << std::dec << std::endl; throw std::runtime_error(what); }
}
struct Report {
  std::filesystem::path path;
  std::vector<std::pair<std::string,bool>> checks;
  void Check(const char* name, bool pass) {
    checks.emplace_back(name,pass);
    std::ofstream out(path); out << "{\"checks\":[";
    for(size_t i=0;i<checks.size();++i) {
      if(i)out<<',';
      out<<"{\"name\":\""<<checks[i].first<<"\",\"passed\":"<<(checks[i].second?"true":"false")<<'}';
    }
    out<<"]}\n"; out.close();
    std::cout<<(pass?"PASS ":"FAIL ")<<name<<std::endl;
    if(!pass)throw std::runtime_error(name);
  }
};
static void Pump(unsigned ms=40) {
  ULONGLONG end=GetTickCount64()+ms;
  do {
    MSG msg;
    while(PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    if(GetTickCount64()<end) MsgWaitForMultipleObjects(0,nullptr,FALSE,5,QS_ALLINPUT);
  } while(GetTickCount64()<end);
}
class Host {
 public:
  CComPtr<ITfThreadMgr> manager;
  CComPtr<ITfThreadMgr2> isolatedKeys;
  CComPtr<ITfTextInputProcessor> processor;
  CComPtr<ITfKeyEventSink> keys;
  CComPtr<ITfThreadMgrEventSink> lifecycle;
  CComPtr<ITfDocumentMgr> docs[2];
  CComPtr<ITfContext> contexts[2];
  CComPtr<TextStore> stores[2];
  TfClientId client=TF_CLIENTID_NULL;
  HMODULE dll=nullptr;
  HWND window=nullptr;
  int focused=0;
  bool active=false, menuSeen=false, menuUnlocked=false, menuTimedOut=false;
  bool interactive=false;
  std::filesystem::path observation;
  std::function<void()> menuTask;
  void Layout() {
    for(int i=0;i<2;++i) if(stores[i] && stores[i]->window) {
      SetWindowPos(stores[i]->window,nullptr,TextHostPixels(window,20),TextHostPixels(window,60+i*160),
          TextHostPixels(window,850),TextHostPixels(window,135),SWP_NOZORDER|SWP_NOACTIVATE);
      if(stores[i]->sink)stores[i]->sink->OnLayoutChange(TS_LC_CHANGE,1);
    }
    InvalidateRect(window,nullptr,TRUE);
  }
  static LRESULT CALLBACK WindowProc(HWND w,UINT m,WPARAM a,LPARAM b) {
    auto* host=reinterpret_cast<Host*>(GetWindowLongPtrW(w,GWLP_USERDATA));
    if(m==WM_NCCREATE) {
      host=static_cast<Host*>(reinterpret_cast<CREATESTRUCT*>(b)->lpCreateParams);
      host->window=w;
      SetWindowLongPtrW(w,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(host));
    }
    if(host) {
      if(m==WM_PAINT) {
        PAINTSTRUCT ps; auto dc=BeginPaint(w,&ps); RECT rc; GetClientRect(w,&rc);
        FillRect(dc,&rc,reinterpret_cast<HBRUSH>(COLOR_WINDOW+1)); SetBkMode(dc,TRANSPARENT);
        std::wstring title=L"Unregistered TSF text host — real Windows edit sessions";
        auto font=CreateFontW(-TextHostPixels(w,14),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        auto old=SelectObject(dc,font);
        TextOutW(dc,TextHostPixels(w,18),TextHostPixels(w,18),title.c_str(),static_cast<int>(title.size()));
        SelectObject(dc,old); DeleteObject(font);
        EndPaint(w,&ps); return 0;
      }
      if(m==WM_DPICHANGED) {
        const auto& suggested=*reinterpret_cast<RECT*>(b);
        SetWindowPos(w,nullptr,suggested.left,suggested.top,suggested.right-suggested.left,suggested.bottom-suggested.top,
            SWP_NOZORDER|SWP_NOACTIVATE);
        host->Layout(); return 0;
      }
      if(m==WM_TIMER && a==92) {
        KillTimer(w,92);
        EnumThreadWindows(GetCurrentThreadId(),[](HWND menu,LPARAM data)->BOOL {
          wchar_t name[32]{}; GetClassNameW(menu,name,32);
          if(IsWindowVisible(menu) && wcscmp(name,L"#32768")==0) {
            reinterpret_cast<Host*>(data)->menuSeen=true;
          }
          return TRUE;
        },reinterpret_cast<LPARAM>(host));
        host->menuUnlocked=!host->stores[0]->lock && !host->stores[1]->lock;
        if(host->menuTask)host->menuTask(); return 0;
      }
      if(m==WM_TIMER && a==93) { host->menuTimedOut=true; EndMenu(); return 0; }
      if(m==WM_TIMER && a==94) { host->SaveObservation(); return 0; }
      if(m==WM_ACTIVATEAPP && host->interactive && host->active) {
        host->keys->OnSetFocus(a != 0);
      }
      if(m==WM_CLOSE) { DestroyWindow(w); return 0; }
    }
    return DefWindowProcW(w,m,a,b);
  }
  static LRESULT CALLBACK TextProc(HWND w,UINT m,WPARAM a,LPARAM b) {
    auto* host=reinterpret_cast<Host*>(GetWindowLongPtrW(w,GWLP_USERDATA));
    if(m==WM_NCCREATE) {
      host=static_cast<Host*>(reinterpret_cast<CREATESTRUCT*>(b)->lpCreateParams);
      SetWindowLongPtrW(w,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(host));
    }
    if(host) {
      int index=GetDlgCtrlID(w)-100;
      if(m==WM_PAINT && index>=0 && index<2 && host->stores[index]) {
        auto& store=*host->stores[index]; PAINTSTRUCT ps; auto dc=BeginPaint(w,&ps);
        RECT rc; GetClientRect(w,&rc); FillRect(dc,&rc,reinterpret_cast<HBRUSH>(COLOR_WINDOW+1));
        FrameRect(dc,&rc,reinterpret_cast<HBRUSH>(COLOR_WINDOWFRAME+1)); SetBkMode(dc,TRANSPARENT);
        std::wstring label=index?L"Document B":L"Document A";
        auto labelFont=CreateFontW(-TextHostPixels(w,14),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        auto old=SelectObject(dc,labelFont);
        TextOutW(dc,TextHostPixels(w,16),TextHostPixels(w,12),label.c_str(),static_cast<int>(label.size()));
        auto font=CreateFontW(-TextHostPixels(w,24),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        SelectObject(dc,font); TextOutW(dc,TextHostPixels(w,16),TextHostPixels(w,40),store.text.c_str(),static_cast<int>(store.text.size()));
        DeleteObject(labelFont);
        SelectObject(dc,old); DeleteObject(font); EndPaint(w,&ps); return 0;
      }
      if(m==WM_LBUTTONDOWN) { host->Focus(index); return 0; }
      if((m==WM_KEYDOWN || m==WM_KEYUP || m==WM_SYSKEYDOWN || m==WM_SYSKEYUP) && host->active) {
        BOOL eaten=FALSE;
        const bool release=m==WM_KEYUP || m==WM_SYSKEYUP;
        // Forward the actual message and actual modifier state. The synthetic
        // Key() helper belongs only to automated edit-session tests.
        if(release) host->keys->OnKeyUp(host->contexts[index],a,b,&eaten);
        else host->keys->OnKeyDown(host->contexts[index],a,b,&eaten);
        if(eaten)return 0;
      }
    }
    return DefWindowProcW(w,m,a,b);
  }
  void Open(const wchar_t* path) {
    weasel::Client ready;
    bool connected=false;
    for(unsigned i=0;i<300 && !connected;++i) { connected=ready.Connect(); if(!connected)Sleep(10); }
    if(!connected)throw std::runtime_error("Isolated service unavailable");
    ready.Disconnect();
    WNDCLASSW wc{}; wc.hInstance=GetModuleHandleW(nullptr); wc.lpfnWndProc=WindowProc;
    wc.lpszClassName=L"StudyTsfTextHost"; wc.hCursor=LoadCursor(nullptr,IDC_ARROW); RegisterClassW(&wc);
    wc.lpfnWndProc=TextProc; wc.lpszClassName=L"StudyTsfTextStore"; RegisterClassW(&wc);
    window=CreateWindowW(L"StudyTsfTextHost",L"Study IME — isolated TSF host",WS_OVERLAPPEDWINDOW,
        120,120,920,470,nullptr,nullptr,wc.hInstance,this);
    SetWindowPos(window,nullptr,0,0,TextHostPixels(window,920),TextHostPixels(window,470),SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE);
    ShowWindow(window,SW_SHOWNORMAL);
    ImmAssociateContext(window,nullptr);
    Require(manager.CoCreateInstance(CLSID_TF_ThreadMgr),"Create Windows thread manager");
    CComQIPtr<ITfThreadMgrEx> ex(manager);
    Require(ex->ActivateEx(&client,TF_TMAE_NOACTIVATETIP),"Activate isolated application thread");
    // NOACTIVATETIP only defers installed TIP activation until focus. Suspend
    // automatic keystroke routing on this host thread; forward its actual key
    // messages directly below. No profile/keyboard settings are changed.
    Require(manager->QueryInterface(&isolatedKeys),"Get thread-local key isolation");
    Require(isolatedKeys->SuspendKeystrokeHandling(),"Suspend installed TIP key handling in host");
    for(int i=0;i<2;++i) {
      stores[i].Attach(new TextStore);
      stores[i]->window=CreateWindowW(L"StudyTsfTextStore",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP,
          TextHostPixels(window,20),TextHostPixels(window,60+i*160),TextHostPixels(window,850),TextHostPixels(window,135),
          window,reinterpret_cast<HMENU>(static_cast<INT_PTR>(100+i)),wc.hInstance,this);
      ImmAssociateContext(stores[i]->window,nullptr);
      Require(manager->CreateDocumentMgr(&docs[i]),"Create document manager");
      TfEditCookie cookie;
      Require(docs[i]->CreateContext(client,0,static_cast<ITextStoreACP*>(stores[i]),&contexts[i],&cookie),"Create real TSF context");
      Require(docs[i]->Push(contexts[i]),"Push context");
      CComPtr<ITfDocumentMgr> previous;
      Require(manager->AssociateFocus(stores[i]->window,docs[i],&previous),"Associate native text window focus");
    }
    Focus(0);
    dll=LoadLibraryW(path); if(!dll)throw std::runtime_error("Load TSF DLL");
    auto factory=reinterpret_cast<HRESULT(WINAPI*)(REFCLSID,REFIID,void**)>(GetProcAddress(dll,"DllGetClassObject"));
    const CLSID id={0xa3f4cded,0xb1e9,0x41ee,{0x9c,0xa6,0x7b,0x4d,0x0d,0xe6,0xcb,0x0a}};
    CComPtr<IClassFactory> cf;
    Require(factory(id,IID_IClassFactory,reinterpret_cast<void**>(&cf)),"Get in-process factory");
    Require(cf->CreateInstance(nullptr,IID_ITfTextInputProcessor,reinterpret_cast<void**>(&processor)),"Create unregistered TSF");
    Require(processor->QueryInterface(&keys),"Get production key sink");
    Require(processor->QueryInterface(&lifecycle),"Get production lifecycle sink");
    CComQIPtr<ITfClientId> ids(manager);
    TfClientId tipClient=TF_CLIENTID_NULL;
    if(!ids)throw std::runtime_error("Get TSF client identity provider");
    Require(ids->GetClientId(id,&tipClient),"Get process-local TIP client identity");
    Require(processor->Activate(manager,tipClient),"Activate production TSF"); active=true;
    keys->OnSetFocus(TRUE); Pump();
  }
  void Focus(int index) {
    if(index<0 || index>1)return;
    CComPtr<ITfDocumentMgr> previous; manager->GetFocus(&previous);
    focused=index; SetFocus(stores[index]->window);
    Require(manager->SetFocus(docs[index]),"Switch document focus");
    // NOACTIVATETIP deliberately suppresses automatic TIP routing. The host
    // delivers lifecycle events to the same production interface as Windows.
    if(lifecycle && previous!=docs[index]) lifecycle->OnSetFocus(docs[index],previous);
    if(keys)keys->OnSetFocus(TRUE);
  }
  void Key(UINT key,bool ctrl=false,bool shift=false,bool test=true,bool alt=false) {
    BYTE saved[256]{}, state[256]{}; GetKeyboardState(saved);
    state[key]=0x80; if(ctrl)state[VK_CONTROL]=0x80; if(shift)state[VK_SHIFT]=0x80;
    if(alt)state[VK_MENU]=0x80;
    SetKeyboardState(state);
    LPARAM info=1 | (static_cast<LPARAM>(MapVirtualKeyW(key,MAPVK_VK_TO_VSC))<<16);
    BOOL eaten=FALSE;
    if(test) {
      Require(keys->OnTestKeyDown(contexts[focused],key,info,&eaten),"Test key down");
      if(eaten) Require(keys->OnTestKeyDown(contexts[focused],key,info,&eaten),"Repeated test key down");
    }
    Require(keys->OnKeyDown(contexts[focused],key,info,&eaten),"Key down");
    SetKeyboardState(saved);
  }
  void Type(const char* value) { for(;*value;++value) { Key(static_cast<UINT>(toupper(*value))); Pump(8); } }
  HWND Candidate() {
    HWND result=nullptr;
    EnumThreadWindows(GetCurrentThreadId(),[](HWND w,LPARAM p)->BOOL {
      wchar_t name[64]{}; GetClassNameW(w,name,64);
      if(IsWindowVisible(w) && wcscmp(name,L"StudyImeCandidateV05")==0)
        *reinterpret_cast<HWND*>(p)=w;
      return TRUE;
    },reinterpret_cast<LPARAM>(&result));
    return result;
  }
  HWND Definition() {
    HWND result=nullptr;
    EnumThreadWindows(GetCurrentThreadId(),[](HWND w,LPARAM p)->BOOL {
      wchar_t name[64]{}; GetClassNameW(w,name,64);
      if(IsWindowVisible(w) && wcscmp(name,L"StudyImeDefinitionV05")==0) *reinterpret_cast<HWND*>(p)=w;
      return TRUE;
    },reinterpret_cast<LPARAM>(&result));
    return result;
  }
  CComPtr<IAccessible> Access() {
    CComPtr<IAccessible> accessible;
    HWND window=Candidate();
    if(!window)throw std::runtime_error("No candidate view for accessibility action");
    Require(AccessibleObjectFromWindow(window,OBJID_CLIENT,IID_IAccessible,reinterpret_cast<void**>(&accessible)),"Candidate accessibility");
    return accessible;
  }
  CComPtr<ITfCandidateListUIElementBehavior> List() {
    CComQIPtr<ITfUIElementMgr> ui(manager);
    CComPtr<IEnumTfUIElements> elements; Require(ui->EnumUIElements(&elements),"Enumerate TSF UI elements");
    CComPtr<ITfUIElement> element;
    ULONG fetched=0;
    while(elements->Next(1,&element,&fetched)==S_OK && fetched) {
      CComQIPtr<ITfCandidateListUIElementBehavior> candidate(element);
      if(candidate)return CComPtr<ITfCandidateListUIElementBehavior>(candidate);
      element.Release();
    }
    throw std::runtime_error("No TSF candidate list element");
  }
  std::wstring CandidateText(unsigned index) {
    auto list=List(); CComBSTR value; Require(list->GetString(index,&value),"TSF candidate text");
    return std::wstring(value,value.Length());
  }
  unsigned Selection() { auto list=List(); UINT selected=0; Require(list->GetSelection(&selected),"TSF selection"); return selected; }
  void Tool(int offset) {
    auto accessible=Access(); LONG count=0; Require(accessible->get_accChildCount(&count),"Accessible child count");
    VARIANT child{}; child.vt=VT_I4; child.lVal=count-3+offset;
    Require(accessible->accDoDefaultAction(child),"Accessible toolbar action"); Pump();
  }
  void Menu(std::function<void()> action) {
    menuSeen=false; menuUnlocked=false; menuTimedOut=false; menuTask=std::move(action);
    SetTimer(window,92,180,nullptr);
    SetTimer(window,93,2500,nullptr);
    Key(VK_APPS); KillTimer(window,92); KillTimer(window,93); menuTask={}; Pump();
    if(menuTimedOut)throw std::runtime_error("Native menu did not close without the host safety timeout");
  }
  void SaveObservation() {
    if(observation.empty() || !stores[0] || !stores[1])return;
    std::ofstream out(observation);
    out<<"{\"focused\":"<<focused<<",\"candidateVisible\":"<<(Candidate()?"true":"false")<<",\"documents\":[";
    for(int i=0;i<2;++i) {
      if(i)out<<',';
      out<<"{\"utf16\":[";
      for(size_t n=0;n<stores[i]->text.size();++n) { if(n)out<<','; out<<static_cast<unsigned>(stores[i]->text[n]); }
      out<<"],\"compositions\":"<<stores[i]->compositions<<",\"writes\":"<<stores[i]->writes.size()
          <<",\"lockViolations\":"<<stores[i]->violations<<'}';
    }
    out<<"]}\n";
  }
  void Close() {
    if(active) { processor->Deactivate(); active=false; }
    lifecycle.Release(); keys.Release(); processor.Release();
    if(manager) {
      manager->SetFocus(nullptr);
      for(int i=0;i<2;++i) {
        CComPtr<ITfDocumentMgr> previous;
        if(stores[i])manager->AssociateFocus(stores[i]->window,nullptr,&previous);
        if(docs[i])docs[i]->Pop(TF_POPF_ALL); contexts[i].Release(); docs[i].Release();
      }
      if(isolatedKeys) { isolatedKeys->ResumeKeystrokeHandling(); isolatedKeys.Release(); }
      manager->Deactivate(); manager.Release();
    }
    for(auto& store:stores)store.Release();
    if(window)DestroyWindow(window); window=nullptr;
  }
  ~Host() { Close(); }
};

static void NativeUiChecks(Host& host,Report& report) {
  auto& a=*host.stores[0]; auto& b=*host.stores[1];
  report.Check("TSF host and text stores start per-monitor V2 aware",
      AreDpiAwarenessContextsEqual(GetThreadDpiAwarenessContext(),DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) &&
      AreDpiAwarenessContextsEqual(GetWindowDpiAwarenessContext(host.window),DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) &&
      GetDpiForWindow(a.window)==GetDpiForWindow(host.window) && GetDpiForWindow(b.window)==GetDpiForWindow(host.window));
  host.Type("nihao");
  const UINT candidateDpi=GetDpiForWindow(host.Candidate());
  RECT pixels{}; GetWindowRect(host.Candidate(),&pixels);
  report.Check("TSF candidate uses monitor DPI and a native physical-pixel surface",
      candidateDpi==GetDpiForWindow(host.window) && candidateDpi>0 &&
      AreDpiAwarenessContextsEqual(GetWindowDpiAwarenessContext(host.Candidate()),DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) &&
      abs((pixels.bottom-pixels.top)-MulDiv(55,candidateDpi,96))<=1);
  std::cout<<"Native candidate DPI: "<<candidateDpi<<"; physical pixels: "
      <<pixels.right-pixels.left<<'x'<<pixels.bottom-pixels.top<<std::endl;
  auto access=host.Access(); LONG children=0; access->get_accChildCount(&children);
  report.Check("native v0.5 candidate exposes current candidates and four accessible tools",children>=5 && host.Candidate());
  const auto selectedText=host.CandidateText(1);
  report.Check("TSF candidate BSTR contains no embedded terminator",!selectedText.empty() && selectedText.find(L'\0')==std::wstring::npos);
  VARIANT second{}; second.vt=VT_I4; second.lVal=2;
  Require(access->accDoDefaultAction(second),"Ordinary accessible candidate action"); Pump();
  report.Check("ordinary nonhighlighted candidate action commits Chinese through TSF once",a.text==selectedText && a.compositions==0);
  LONG staleCount=-1; access->get_accChildCount(&staleCount);
  report.Check("retained accessibility object cannot act on a destroyed view",staleCount==0 && FAILED(access->accDoDefaultAction(second)) && a.text==selectedText);
  access.Release();
  host.Type("nihao");
  { auto list=host.List(); Require(list->SetSelection(1),"TSF selection callback"); }
  const auto selectedAgain=host.CandidateText(1);
  { auto list=host.List(); Require(list->Finalize(),"TSF finalize Chinese"); }
  Pump();
  report.Check("TSF UI element selection and finalize share the Chinese commit path",a.text==selectedText+selectedAgain && a.compositions==0);
  host.Type("nihao");
  RECT bar{}; GetWindowRect(host.Candidate(),&bar);
  auto before=a.text; auto writes=a.writes.size();
  host.Key(VK_F2); Pump(); RECT after{}; GetWindowRect(host.Candidate(),&after);
  report.Check("F2 opens separate definition without an edit or candidate resize",host.Definition() && a.text==before && a.writes.size()==writes && EqualRect(&bar,&after));
  host.Key(VK_ESCAPE); Pump();
  report.Check("Escape closes definition while preserving composition",!host.Definition() && a.text==before && a.compositions==1);
  host.Key(VK_RETURN,true,true); Pump();
  const auto english=a.text;
  host.Key(VK_RETURN,true,true); Pump();
  report.Check("explicit English still commits exactly once after closing definition",english==selectedText+selectedAgain+L"hello" && a.text==english);

  host.Type("shishi"); host.Tool(1);
  { auto list=host.List(); Require(list->SetSelection(1),"Select page-two candidate"); }
  const auto first=host.CandidateText(0), chosen=host.CandidateText(1);
  const unsigned selection=host.Selection();
  GetWindowRect(host.Candidate(),&bar); before=a.text;
  host.Tool(2); Pump(280);
  GetWindowRect(host.Candidate(),&after);
  report.Check("learning tool preserves page selection and composition through real IPC",host.CandidateText(0)==first && host.Selection()==selection && a.text==before && a.compositions==1);
  report.Check("real candidate window contracts while retaining width and top",after.right-after.left==bar.right-bar.left && after.top==bar.top && after.bottom-after.top<bar.bottom-bar.top);
  access=host.Access(); VARIANT one{}; one.vt=VT_I4; one.lVal=1; CComBSTR accessibleName;
  access->get_accName(one,&accessibleName);
  report.Check("learning-off accessible candidates omit English immediately",std::wstring(accessibleName).find(L'，')==std::wstring::npos);
  access.Release();
  host.Key(VK_RETURN,true,true); Pump();
  report.Check("learning-off rejects explicit English without losing composition",a.text==before && a.compositions==1);
  report.Check("learning-off preference is persisted locally",!study::LoadPreferences(study::PreferencesPath()).learning);
  host.Tool(2); Pump(280);
  report.Check("learning reenable preserves page and persists enabled state",host.CandidateText(0)==first && host.Selection()==selection && study::LoadPreferences(study::PreferencesPath()).learning);
  host.Key(VK_SPACE); Pump();
  report.Check("Chinese selection remains correct after learning animation",a.text==english+chosen && a.compositions==0);

  auto preference=study::LoadPreferences(study::PreferencesPath());
  preference.learning=false;
  Require(study::SavePreferences(study::PreferencesPath(),preference)?S_OK:E_FAIL,"Save disabled learning externally");
  host.Type("nihao"); before=a.text; host.Key(VK_RETURN,true,true); Pump();
  report.Check("externally saved learning preference updates the existing service session",a.text==before && a.compositions==1);
  host.Key(VK_ESCAPE); Pump();
  preference.learning=true;
  preference.shortcut=study::EnglishShortcut::AltEnter;
  Require(study::SavePreferences(study::PreferencesPath(),preference)?S_OK:E_FAIL,"Save alternate shortcut");
  host.Type("nihao"); before=a.text;
  access=host.Access(); CComBSTR enabledName; access->get_accName(one,&enabledName); access.Release();
  report.Check("externally reenabled learning restores English on the next composition",std::wstring(enabledName).find(L"hello")!=std::wstring::npos);
  host.Key(VK_RETURN,true,true); Pump();
  report.Check("alternate shortcut disables the default Lua English chord",a.text==before && a.compositions==1);
  host.Key(VK_RETURN,false,false,true,true); Pump();
  report.Check("configured Alt Enter commits complete English through TSF",a.text==english+chosen+L"hello" && a.compositions==0);
  host.Type("nihao"); before=a.text;
  host.Key(VK_F12,true,true); Pump();
  report.Check("settings shortcut during composition preserves pending input",a.text==before && a.compositions==1 && !FindWindowW(L"StudyImeSettings",nullptr));
  host.Key(VK_F2); Pump(); host.Focus(1); Pump();
  report.Check("document focus change closes definition and old candidate view",!host.Definition() && !host.Candidate());
  host.Type("nihao"); host.Key(VK_SPACE); Pump();
  report.Check("new document accepts Chinese after definition focus change",b.text==L"你好" && b.compositions==0);
  host.Type("nihao"); host.Key(VK_F2); Pump();
  access=host.Access();
  weasel::Client stopper; if(!stopper.Connect())throw std::runtime_error("Connect UI disconnect stopper");
  const auto start=GetTickCount64(); stopper.ShutdownServer(); Pump(650);
  report.Check("visible candidate and definition close on service loss without a key",!host.Candidate() && !host.Definition() && GetTickCount64()-start<2000);
  before=b.text; host.Key(VK_RETURN,false,false,true,true); Pump();
  report.Check("disconnected alternate English action is never replayed",b.text==before);
  report.Check("native UI actions respect all actual TSF edit locks",a.violations==0 && b.violations==0);
  host.Close();
  auto canUnload=reinterpret_cast<HRESULT(WINAPI*)()>(GetProcAddress(host.dll,"DllCanUnloadNow"));
  report.Check("retained accessibility reference keeps the DLL alive safely",canUnload && canUnload()==S_FALSE);
  access.Release();
  report.Check("releasing accessibility permits complete TSF DLL teardown",canUnload && canUnload()==S_OK);
}

int wmain(int argc,wchar_t** argv) {
  if(argc<3)return 2;
  Require(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED),"COM apartment");
  Report report{argv[1]};
  try {
    Host host;
    host.interactive=argc>3 && wcscmp(argv[3],L"--interactive")==0;
    if(host.interactive)host.observation=argv[1];
    host.Open(argv[2]);
    if(host.interactive) {
      SetTimer(host.window,94,200,nullptr);
      std::cout<<"Interactive text host ready; physical key messages forwarded to production TSF sinks."<<std::endl;
      while(IsWindow(host.window))Pump(20);
      host.SaveObservation(); host.Close();
      auto canUnload=reinterpret_cast<HRESULT(WINAPI*)()>(GetProcAddress(host.dll,"DllCanUnloadNow"));
      if(!canUnload || canUnload()!=S_OK)throw std::runtime_error("Interactive DLL still referenced");
      FreeLibrary(host.dll); host.dll=nullptr;
      CoUninitialize(); return 0;
    }
    if(argc>3 && wcscmp(argv[3],L"--v05")==0) {
      NativeUiChecks(host,report);
      FreeLibrary(host.dll); host.dll=nullptr;
      CoUninitialize(); return 0;
    }
    auto& a=*host.stores[0]; auto& b=*host.stores[1];
    report.Check("unregistered production TSF activated with two real text contexts",host.active && a.sink && b.sink);
    host.Type("nihao");
    report.Check("real composition writes under synchronous text-store lock",a.syncGrants>0 && a.compositions==1 && !a.text.empty() && a.violations==0);
    report.Check("production candidate popup is visible",host.Candidate()!=nullptr);
    if(GetEnvironmentVariableW(L"STUDY_TSF_PREVIEW",nullptr,0)) Pump(60000);
    host.Key(VK_SPACE); Pump();
    report.Check("space commits Chinese through ITfRange exactly once",a.text==L"你好" && a.compositions==0);
    host.Type("nihao"); host.Key(VK_RETURN,true,true); Pump();
    report.Check("explicit English action commits through real TSF range",a.text==L"你好hello" && a.compositions==0);
    if(GetEnvironmentVariableW(L"STUDY_TSF_PREVIEW",nullptr,0)) Pump(30000);
    host.Key(VK_RETURN,true,true); Pump();
    report.Check("repeated explicit action cannot duplicate English",a.text==L"你好hello");
    host.Type("nihao"); auto before=a.text;
    a.defer=true; host.Key(VK_RETURN,true,true);
    report.Check("application defers actual TSF write grant",a.pending && a.text==before);
    // Later IPC overwrites the transport while the first commit awaits its lock.
    host.Key('N');
    a.Drain(); Pump();
    report.Check("deferred owned commit survives later key response",a.text.find(L"你好hellohello")==0 && a.asyncGrants>0 && a.violations==0);
    host.Key(VK_ESCAPE); Pump();
    host.Type("nihao"); a.defer=true; host.Key(VK_RETURN,true,true);
    host.Focus(1); host.Type("nihao"); auto composingB=b.text;
    a.Drain(); Pump();
    report.Check("focus switch rejects queued commit in both documents",a.text.find(L"hellohellohello")==std::wstring::npos && b.text==composingB);
    host.Key(VK_SPACE); Pump();
    report.Check("new focused document owns its composition and commit",b.text==L"你好" && b.compositions==0);
    host.Type("nihao");
    host.Menu([&]{ EndMenu(); });
    report.Check("native TSF menu opens outside write lock and cancels",host.menuSeen && host.menuUnlocked && b.text!=L"你好hello");
    host.Menu([&]{ host.Focus(0); });
    report.Check("focus change closes actual modal TSF menu",host.menuSeen && host.focused==0);
    host.Key(VK_ESCAPE); Pump(); host.Type("nihao");
    weasel::Client stopper; if(!stopper.Connect())throw std::runtime_error("Connect isolated stopper");
    auto start=GetTickCount64();
    host.Menu([&]{ stopper.ShutdownServer(); });
    report.Check("service disconnect closes native menu by watchdog",host.menuSeen && GetTickCount64()-start<2000);
    auto disconnected=a.text; host.Key(VK_RETURN,true,true); Pump();
    report.Check("disconnected English action does not replay or insert",a.text==disconnected);
    report.Check("all real TSF document writes respected edit locks",a.violations==0 && b.violations==0);
    host.Close();
    auto canUnload=reinterpret_cast<HRESULT(WINAPI*)()>(GetProcAddress(host.dll,"DllCanUnloadNow"));
    report.Check("deactivation releases frontend COM lifetime",canUnload && canUnload()==S_OK);
    FreeLibrary(host.dll); host.dll=nullptr;
    CoUninitialize(); return 0;
  } catch(const std::exception& error) { std::cerr<<error.what()<<std::endl; CoUninitialize(); return 1; }
}

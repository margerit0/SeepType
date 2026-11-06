#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "text_store.h"
#include <WeaselIPC.h>
#include <imm.h>
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
  std::function<void()> menuTask;
  static LRESULT CALLBACK WindowProc(HWND w,UINT m,WPARAM a,LPARAM b) {
    auto* host=reinterpret_cast<Host*>(GetWindowLongPtrW(w,GWLP_USERDATA));
    if(m==WM_NCCREATE) {
      host=static_cast<Host*>(reinterpret_cast<CREATESTRUCT*>(b)->lpCreateParams);
      SetWindowLongPtrW(w,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(host));
    }
    if(host) {
      if(m==WM_PAINT) {
        PAINTSTRUCT ps; auto dc=BeginPaint(w,&ps); RECT rc; GetClientRect(w,&rc);
        FillRect(dc,&rc,reinterpret_cast<HBRUSH>(COLOR_WINDOW+1)); SetBkMode(dc,TRANSPARENT);
        std::wstring title=L"Unregistered TSF text host — real Windows edit sessions";
        TextOutW(dc,18,18,title.c_str(),static_cast<int>(title.size()));
        EndPaint(w,&ps); return 0;
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
        TextOutW(dc,16,12,label.c_str(),static_cast<int>(label.size()));
        auto font=CreateFontW(-24,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        auto old=SelectObject(dc,font); TextOutW(dc,16,40,store.text.c_str(),static_cast<int>(store.text.size()));
        SelectObject(dc,old); DeleteObject(font); EndPaint(w,&ps); return 0;
      }
      if(m==WM_LBUTTONDOWN) { host->Focus(index); return 0; }
      if(m==WM_KEYDOWN && host->active) { host->Key(static_cast<UINT>(a),false,false,false); return 0; }
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
    window=CreateWindowW(L"StudyTsfTextHost",L"Study IME — isolated TSF host",WS_OVERLAPPEDWINDOW|WS_VISIBLE,
        120,120,920,470,nullptr,nullptr,wc.hInstance,this);
    ImmAssociateContext(window,nullptr);
    Require(manager.CoCreateInstance(CLSID_TF_ThreadMgr),"Create Windows thread manager");
    CComQIPtr<ITfThreadMgrEx> ex(manager);
    Require(ex->ActivateEx(&client,TF_TMAE_NOACTIVATETIP),"Activate isolated application thread");
    for(int i=0;i<2;++i) {
      stores[i].Attach(new TextStore);
      stores[i]->window=CreateWindowW(L"StudyTsfTextStore",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP,
          20,60+i*160,850,135,window,reinterpret_cast<HMENU>(static_cast<INT_PTR>(100+i)),wc.hInstance,this);
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
  void Key(UINT key,bool ctrl=false,bool shift=false,bool test=true) {
    BYTE saved[256]{}, state[256]{}; GetKeyboardState(saved);
    state[key]=0x80; if(ctrl)state[VK_CONTROL]=0x80; if(shift)state[VK_SHIFT]=0x80;
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
      // WTL uses an ATL-generated class name for this production panel.
      const auto style=GetWindowLongPtrW(w,GWL_EXSTYLE);
      if(IsWindowVisible(w) && (style & WS_EX_LAYERED) && (style & WS_EX_NOACTIVATE))
        *reinterpret_cast<HWND*>(p)=w;
      return TRUE;
    },reinterpret_cast<LPARAM>(&result));
    return result;
  }
  void Menu(std::function<void()> action) {
    menuSeen=false; menuUnlocked=false; menuTimedOut=false; menuTask=std::move(action);
    SetTimer(window,92,180,nullptr);
    SetTimer(window,93,2500,nullptr);
    Key(VK_APPS); KillTimer(window,92); KillTimer(window,93); menuTask={}; Pump();
    if(menuTimedOut)throw std::runtime_error("Native menu did not close without the host safety timeout");
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
      manager->Deactivate(); manager.Release();
    }
    for(auto& store:stores)store.Release();
    if(window)DestroyWindow(window); window=nullptr;
  }
  ~Host() { Close(); }
};

int wmain(int argc,wchar_t** argv) {
  if(argc<3)return 2;
  Require(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED),"COM apartment");
  Report report{argv[1]};
  try {
    Host host; host.Open(argv[2]);
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

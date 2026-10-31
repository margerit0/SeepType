// Interactive, isolated native window using real WeaselUI and the bundled DLL.
#include "stdafx.h"
#include "StudyLayout.h"
#include "WeaselPanel.h"
#include "HorizontalLayout.h"
#include "StudyEngine.h"
#include "../../src/study/windows/EnglishMenu.h"
#include <fstream>
#include <filesystem>
#include <memory>
#include <iomanip>
#include <sstream>
#include <dbghelp.h>
#include <imm.h>
#pragma comment(lib,"dbghelp.lib")
#pragma comment(lib,"imm32.lib")

CAppModule _Module;
static std::unique_ptr<study::Engine> engine;
static study::Snapshot snapshot;
static std::unique_ptr<weasel::UI> ui;
static HWND outputBox, inputLabel, learningButton;
static std::wstring output;
static std::filesystem::path root;
static weasel::Context current;
static weasel::Status status;
static const char* phase="startup";
static bool automated=false;
static bool darkTheme=false;
static std::string captureName;
static bool frameCaptured=false;
static bool englishMenuOpen=false;
static void showEnglishMenu(HWND window,size_t index,POINT position);
static LRESULT CALLBACK studyPanelSubclass(HWND,UINT,WPARAM,LPARAM,UINT_PTR,DWORD_PTR);
static UINT windowDpi(HWND window) {
  auto query=reinterpret_cast<UINT(WINAPI*)(HWND)>(GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetDpiForWindow"));
  return query?query(window):96;
}

// Only inspect popup windows created by this test process on this thread.
static HWND panelWindow(HWND owner) {
  const ATOM candidateClass=WeaselPanel::GetWndClassInfo().m_atom;
  if(!candidateClass)return nullptr;
  struct Search {HWND owner;HWND found;ATOM candidateClass;};
  Search search{owner,nullptr,candidateClass};
  EnumThreadWindows(GetCurrentThreadId(),[](HWND window,LPARAM data)->BOOL {
    auto& result=*reinterpret_cast<Search*>(data);
    if(GetWindow(window,GW_OWNER)==result.owner &&
        static_cast<ATOM>(GetClassLongPtr(window,GCW_ATOM))==result.candidateClass) {
      result.found=window;return FALSE;
    }
    return TRUE;
  },reinterpret_cast<LPARAM>(&search));
  return search.found;
}

void weasel::CaptureStudyFrame(HDC source,int width,int height) {
  if(captureName.empty() || width<=0 || height<=0)return;
  BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
  info.bmiHeader.biWidth=width;info.bmiHeader.biHeight=-height;
  info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
  void* pixels=nullptr;
  HBITMAP bitmap=CreateDIBSection(source,&info,DIB_RGB_COLORS,&pixels,nullptr,0);
  HDC target=CreateCompatibleDC(source);
  if(bitmap && target) {
    HGDIOBJ old=SelectObject(target,bitmap);
    if(BitBlt(target,0,0,width,height,source,0,0,SRCCOPY)) {
      GdiFlush();
      const auto directory=root/L"experiments/phase3/runtime/frames";
      std::filesystem::create_directories(directory);
      std::ofstream data(directory/(captureName+".bgra"),std::ios::binary);
      data.write(static_cast<const char*>(pixels),static_cast<std::streamsize>(width)*height*4);
      std::ofstream metadata(directory/(captureName+".json"));
      metadata << "{\"width\":" << width << ",\"height\":" << height << '}';
      frameCaptured=data.good() && metadata.good();
    }
    SelectObject(target,old);
  }
  if(target)DeleteDC(target);
  if(bitmap)DeleteObject(bitmap);
  captureName.clear();
}

static std::wstring wide(const char* text) {return string_to_wstring(text?text:"",CP_UTF8);}
static void style(weasel::UIStyle& s) {
  s.font_face=L"Microsoft YaHei";s.label_font_face=s.comment_font_face=L"Segoe UI";
  s.font_point=13;s.label_font_point=10;s.comment_font_point=9;
  s.layout_type=weasel::UIStyle::LAYOUT_HORIZONTAL;s.inline_preedit=true;s.client_caps=1;
  s.margin_x=3;s.margin_y=2;s.border=1;s.candidate_spacing=2;
  s.round_corner=10;s.round_corner_ex=14;s.label_text_format=L"%s";
  s.back_color=0xfffafafa;s.border_color=0xffe3ded9;
  s.text_color=s.candidate_text_color=s.hilited_candidate_text_color=0xff2b2520;
  s.label_text_color=s.hilited_label_text_color=s.comment_text_color=0xff6d6359;
  s.hilited_comment_text_color=0xff9a5b24;s.hilited_candidate_back_color=0xfffff2e9;
  s.hilited_mark_color=0;s.antialias_mode=weasel::UIStyle::GRAYSCALE;
}
static void applyColors(weasel::UIStyle& s,bool learning) {
  s.back_color=darkTheme?0xff242220:0xfffafafa;
  s.border_color=darkTheme?0xff4d4741:0xffe3ded9;
  s.text_color=s.candidate_text_color=s.hilited_candidate_text_color=darkTheme?0xffeee8e2:0xff2b2520;
  s.label_text_color=s.hilited_label_text_color=darkTheme?0xffb4aaa0:0xff6d6359;
  s.comment_text_color=learning?(darkTheme?0xffb4aaa0:0xff6d6359):0;
  s.hilited_comment_text_color=learning?(darkTheme?0xffffbe85:0xff9a5b24):0;
  s.hilited_candidate_back_color=darkTheme?0xff574330:0xfffff2e9;
}
static void readContext() {
  current=weasel::Context();status=weasel::Status();
  snapshot=engine->Read();
  current.cinfo.currentPage=snapshot.page;current.cinfo.is_last_page=snapshot.last_page;
  current.cinfo.highlighted=snapshot.highlighted;
    for(size_t i=0;i<snapshot.candidates.size();++i) {
      current.cinfo.candies.emplace_back(wide(snapshot.candidates[i].text.c_str()));
      current.cinfo.comments.emplace_back(wide(snapshot.candidates[i].comment.c_str()));
      current.cinfo.labels.emplace_back(std::to_wstring(i+1));
    }
  status.composing=!current.cinfo.candies.empty();
}
static void refresh(HWND window) {
  readContext();
  const bool enabled=snapshot.learning;
  applyColors(ui->style(),enabled);
  // Weasel destroys its popup after a mouse commit. Recreate it for the next
  // composition, just as the real frontend starts a new candidate UI.
  const bool recreated=!panelWindow(window);
  if(recreated){phase="UI.Create";ui->Create(window);}
  if(HWND panel=panelWindow(window))
    SetWindowSubclass(panel,studyPanelSubclass,1,reinterpret_cast<DWORD_PTR>(window));
  const bool styleChanged=ui->ostyle()!=ui->style();
  const bool contextChanged=ui->ctx()!=current || !(ui->status()==status);
  if(styleChanged)ui->octx()=weasel::Context();
  phase="UI.Update";ui->Update(current,status);
  if((styleChanged || recreated) && !contextChanged)ui->Refresh();
  POINT point{24,190};ClientToScreen(window,&point);
  phase="UI.UpdateInputPosition";ui->UpdateInputPosition(RECT{point.x,point.y,point.x+1,point.y+20});
  const bool active=GetForegroundWindow()==window;
  phase="UI.Show";if(status.composing && !automated && active)ui->Show();else ui->Hide();
  output+=wide(snapshot.commit.c_str());
  SetWindowTextW(outputBox,output.c_str());
  std::wstring label=L"拼音："+wide(snapshot.input.c_str())+L"   第 "+std::to_wstring(current.cinfo.currentPage+1)+L" 页";
  SetWindowTextW(inputLabel,label.c_str());
  SetWindowTextW(learningButton,enabled?L"学习：开（F8）":L"学习：关（F8）");
}
static void showEnglishMenu(HWND window,size_t index,POINT position) {
  if(englishMenuOpen)return;
  const auto target=engine->PrepareEnglish(index);
  refresh(window);
  englishMenuOpen=true;
  const UINT selected=study::ShowEnglishMenu(window,position,target);
  englishMenuOpen=false;
  if(selected==study::kInputEnglish)engine->CommitEnglish(target);
  refresh(window);
  if(!automated && GetForegroundWindow()==window)SetFocus(window);
}
static LRESULT CALLBACK studyPanelSubclass(HWND panel,UINT message,WPARAM wp,LPARAM lp,UINT_PTR id,DWORD_PTR data) {
  if(message==WM_RBUTTONUP) {
    const HWND owner=reinterpret_cast<HWND>(data);
    const CPoint point(static_cast<short>(LOWORD(lp)),static_cast<short>(HIWORD(lp)));
    auto resources=std::make_shared<weasel::DirectWriteResources>(ui->style(),windowDpi(panel));
    weasel::StudyLayout layout(ui->style(),current,status,resources);
    HDC dc=GetDC(panel);layout.DoLayout(dc,resources);ReleaseDC(panel,dc);
    for(size_t i=0;i<current.cinfo.candies.size();++i) {
      if(layout.GetCandidateRect(static_cast<int>(i)).PtInRect(point)) {
        POINT screen=point;ClientToScreen(panel,&screen);
        showEnglishMenu(owner,i,screen);return 0;
      }
    }
    return 0;
  }
  if(message==WM_NCDESTROY)RemoveWindowSubclass(panel,studyPanelSubclass,id);
  return DefSubclassProc(panel,message,wp,lp);
}
static void type(const char* text) {engine->Type(text);}
static HWND control(HWND parent,const wchar_t* cls,const wchar_t* text,int id,int x,int y,int w,int h,DWORD extra=0) {
  HWND child=CreateWindowW(cls,text,WS_CHILD|WS_VISIBLE|extra,x,y,w,h,parent,(HMENU)(INT_PTR)id,_Module.GetModuleInstance(),nullptr);
  ImmAssociateContext(child,nullptr);
  SendMessage(child,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);return child;
}
static LRESULT procedureBody(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_CREATE) {
    // This host feeds physical keys into its own isolated Rime session. Detach
    // the installed system IME from this window so it cannot consume them first.
    ImmAssociateContext(window,nullptr);
    control(window,L"STATIC",L"真实 WeaselUI + librime/Lua · 隔离验证，不注册系统输入法",0,20,12,640,24);
    control(window,L"BUTTON",L"苹果",101,20,42,120,30);
    control(window,L"BUTTON",L"多候选",102,150,42,120,30);
    control(window,L"BUTTON",L"长英文",103,280,42,120,30);
    control(window,L"BUTTON",L"没有释义",104,410,42,120,30);
    control(window,L"BUTTON",L"上一页",105,20,82,110,30);
    control(window,L"BUTTON",L"下一页",106,140,82,110,30);
    learningButton=control(window,L"BUTTON",L"学习：开（F8）",107,260,82,130,30);
    control(window,L"BUTTON",L"输入英文",108,400,82,130,30);
    control(window,L"BUTTON",L"浅/深色",109,540,82,110,30);
    inputLabel=control(window,L"STATIC",L"",0,20,126,630,26);
    outputBox=control(window,L"EDIT",L"",0,20,156,630,30,WS_BORDER|ES_READONLY|ES_AUTOHSCROLL);
    ui->SetUICallBack([window](size_t* selected,size_t* highlight,bool* next,bool*){
      if(selected)engine->Select(*selected);
      if(highlight)engine->Highlight(*highlight);
      if(next)engine->Key(*next?65366:65365);
      refresh(window);
    });
    type("pingguo");refresh(window);return 0;
  }
  if(message==WM_COMMAND) {
    switch(LOWORD(wp)) {
      case 101:type("pingguo");break;case 102:type("shishi");break;
      case 103:type("zhishichanquan");break;case 104:type("zhangxiaoming");break;
      case 105:engine->Key(65365);break;case 106:engine->Key(65366);break;
      case 107:engine->Key(65477);break;
      case 108:engine->CommitEnglish(engine->PrepareEnglish(static_cast<size_t>(snapshot.highlighted)));break;
      case 109:darkTheme=!darkTheme;break;
      default:return DefWindowProc(window,message,wp,lp);
    }
    refresh(window);if(!automated)SetFocus(window);return 0;
  }
  if(message==WM_CONTEXTMENU) {
    POINT position{24,190};
    if(lp==static_cast<LPARAM>(-1))ClientToScreen(window,&position);
    else position={static_cast<short>(LOWORD(lp)),static_cast<short>(HIWORD(lp))};
    showEnglishMenu(window,static_cast<size_t>(snapshot.highlighted),position);return 0;
  }
  if(message==WM_KEYDOWN) {
    int key=0,mask=(GetKeyState(VK_SHIFT)<0?1:0)|(GetKeyState(VK_CONTROL)<0?4:0)|(GetKeyState(VK_MENU)<0?8:0);
    if(wp==VK_F2 && mask==0) {
      POINT position{24,190};ClientToScreen(window,&position);
      showEnglishMenu(window,static_cast<size_t>(snapshot.highlighted),position);return 0;
    }
    if(wp==VK_NEXT)key=65366;else if(wp==VK_PRIOR)key=65365;else if(wp==VK_F8)key=65477;
    else if(wp==VK_RETURN)key=65293;else if(wp==VK_ESCAPE)key=65307;
    else if(wp==VK_DOWN)key=65364;else if(wp==VK_UP)key=65362;
    else if(wp==VK_LEFT)key=65361;else if(wp==VK_RIGHT)key=65363;
    else if(wp==VK_BACK)key=65288;else if(wp==VK_DELETE)key=65535;
    else if(wp==VK_HOME)key=65360;else if(wp==VK_END)key=65367;
    if(key){engine->Key(key,mask);refresh(window);return 0;}
  }
  if(message==WM_CHAR && wp>=32 && wp<127) {engine->Key((int)wp);refresh(window);return 0;}
  if(message==WM_ACTIVATE && engine && ui && outputBox && !automated) {
    if(LOWORD(wp)==WA_INACTIVE) {
      engine->InvalidateActions();
      if(englishMenuOpen)EndMenu();
      ui->Hide();
    } else refresh(window);
    return 0;
  }
  if(message==WM_MOVE && ui && ui->IsShown()){refresh(window);return 0;}
  if(message==WM_DESTROY){ui->Destroy(true);PostQuitMessage(0);return 0;}
  return DefWindowProc(window,message,wp,lp);
}
static int reportException(EXCEPTION_POINTERS* info,UINT message) {
  std::ofstream report(root/L"experiments/phase3/runtime/ui-error.txt");
  report << "phase=" << phase << " message=" << message << " code=" << std::hex << info->ExceptionRecord->ExceptionCode
    << " address=" << info->ExceptionRecord->ExceptionAddress << " module=" << GetModuleHandle(nullptr) << '\n';
  for(DWORD i=0;i<info->ExceptionRecord->NumberParameters;++i)
    report << "parameter[" << i << "]=" << info->ExceptionRecord->ExceptionInformation[i] << '\n';
  const auto symbols=(root/L"experiments/phase3/build").string();
  SymSetOptions(SYMOPT_LOAD_LINES | SYMOPT_UNDNAME | SYMOPT_FAIL_CRITICAL_ERRORS);
  SymInitialize(GetCurrentProcess(),symbols.c_str(),TRUE);
  CONTEXT context=*info->ContextRecord;STACKFRAME64 frame{};
  frame.AddrPC.Offset=context.Eip;frame.AddrPC.Mode=AddrModeFlat;
  frame.AddrFrame.Offset=context.Ebp;frame.AddrFrame.Mode=AddrModeFlat;
  frame.AddrStack.Offset=context.Esp;frame.AddrStack.Mode=AddrModeFlat;
  for(int i=0;i<24;++i) {
    if(!StackWalk64(IMAGE_FILE_MACHINE_I386,GetCurrentProcess(),GetCurrentThread(),&frame,&context,nullptr,SymFunctionTableAccess64,SymGetModuleBase64,nullptr))break;
    report << frame.AddrPC.Offset;
    char buffer[sizeof(SYMBOL_INFO)+MAX_SYM_NAME]{};
    auto symbol=reinterpret_cast<SYMBOL_INFO*>(buffer);
    symbol->SizeOfStruct=sizeof(SYMBOL_INFO);symbol->MaxNameLen=MAX_SYM_NAME;
    DWORD64 displacement=0;
    if(SymFromAddr(GetCurrentProcess(),frame.AddrPC.Offset,&displacement,symbol))
      report << ' ' << symbol->Name << "+0x" << displacement;
    IMAGEHLP_LINE64 source{};source.SizeOfStruct=sizeof(source);DWORD offset=0;
    if(SymGetLineFromAddr64(GetCurrentProcess(),frame.AddrPC.Offset,&offset,&source))
      report << ' ' << source.FileName << ':' << std::dec << source.LineNumber << std::hex;
    report << '\n';
  }
  return EXCEPTION_EXECUTE_HANDLER;
}
static LRESULT CALLBACK procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  __try {return procedureBody(window,message,wp,lp);}
  __except(reportException(GetExceptionInformation(),message)) {ExitProcess(8);}
  return 0;
}

static std::string quote(const std::string& value) {
  std::ostringstream result;result << '"';
  for(unsigned char c:value) {
    if(c=='"' || c=='\\')result << '\\' << c;
    else if(c<32)result << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(c);
    else result << c;
  }
  result << '"';return result.str();
}

static bool selfTest(HWND window) {
  std::ofstream report(root/L"experiments/phase3/results/native-ui.json");
  report << "{\"scope\":\"In-process messages to this host's own native windows; no OS input injection or physical mouse test\",\"checks\":[";
  bool all=true,first=true;
  auto check=[&](const char* name,bool passed) {
    all=all&&passed;
    if(!first)report << ',';first=false;
    report << "{\"name\":" << quote(name) << ",\"passed\":" << (passed?"true":"false")
      << ",\"input\":" << quote(snapshot.input) << ",\"commit\":" << quote(snapshot.commit)
      << ",\"page\":" << snapshot.page << ",\"selected\":" << snapshot.highlighted
      << ",\"learning\":" << (snapshot.learning?"true":"false") << '}';
    report.flush();
  };
  auto command=[&](int id){SendMessage(window,WM_COMMAND,MAKEWPARAM(id,BN_CLICKED),0);};
  auto panelSize=[&]() {
    RECT rect{};HWND panel=panelWindow(window);if(panel)GetClientRect(panel,&rect);
    return CSize(rect.right-rect.left,rect.bottom-rect.top);
  };
  auto capture=[&](const char* name) {
    captureName=name;frameCaptured=false;
    ui->octx()=weasel::Context();ui->Refresh();
    captureName.clear();return frameCaptured;
  };
  auto clickCandidate=[&](int index,bool englishRow) {
    HWND panel=panelWindow(window);
    if(!panel || index<0 || index>=static_cast<int>(current.cinfo.candies.size()))return false;
    auto resources=std::make_shared<weasel::DirectWriteResources>(ui->style(),windowDpi(panel));
    weasel::StudyLayout layout(ui->style(),current,status,resources);
    HDC dc=GetDC(panel);layout.DoLayout(dc,resources);ReleaseDC(panel,dc);
    CPoint point=(englishRow?layout.GetCandidateCommentRect(index):layout.GetCandidateTextRect(index)).CenterPoint();
    // These are local window messages, not SendInput or a global mouse action.
    SendMessage(panel,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(point.x,point.y));
    SendMessage(panel,WM_LBUTTONUP,0,MAKELPARAM(point.x,point.y));
    return true;
  };

  check("ATL initialized and native popup created",
    ATL::_AtlWinModule.cbSize==sizeof(ATL::_ATL_WIN_MODULE) && !ATL::CAtlBaseModule::m_bInitFailed && panelWindow(window));
  auto detachedIme=[](HWND target) {
    HIMC context=ImmGetContext(target);
    if(context)ImmReleaseContext(target,context);
    return context==nullptr;
  };
  check("isolated host and controls do not use the installed system IME",
    detachedIme(window) && detachedIme(outputBox) && detachedIme(learningButton));
  check("real apple candidate with definition",
    snapshot.candidates.size()==5 && snapshot.candidates[0].text=="苹果" && snapshot.candidates[0].comment=="apple");
  const UINT dpi=windowDpi(window);
  const CSize initial=panelSize();
  check("light native frame rendered",capture("native-light"));
  check("popup mouse activation handler preserves host focus",
    SendMessage(panelWindow(window),WM_MOUSEACTIVATE,reinterpret_cast<WPARAM>(window),MAKELPARAM(HTCLIENT,WM_LBUTTONDOWN))==MA_NOACTIVATE);
  bool clicked=clickCandidate(0,true);
  check("clicking the English row commits Chinese",clicked && snapshot.commit=="苹果" && snapshot.input.empty());
  command(101);
  check("popup recreated after mouse commit",panelWindow(window) && panelSize()==initial && snapshot.input=="pingguo");
  clicked=clickCandidate(1,false);
  check("clicking a different Chinese candidate uses its current index",clicked && snapshot.commit=="平果");
  command(101);command(108);
  check("explicit English action commits apple",snapshot.commit=="apple" && snapshot.input.empty());
  const std::wstring committed=output;command(108);
  check("repeated English action cannot duplicate text",output==committed && snapshot.commit.empty());
  command(102);engine->Highlight(2);refresh(window);command(108);
  check("English action uses highlighted candidate",snapshot.commit=="give it a try");
  command(102);command(106);
  check("next page uses real Rime candidates",snapshot.page==1 && !snapshot.candidates.empty() && snapshot.candidates[0].text=="适时");
  check("page two native frame rendered",capture("native-page-two"));
  command(108);
  check("English action after paging uses new page",snapshot.commit=="at the right time");
  command(102);command(106);command(105);
  check("previous page restores first-page candidates",snapshot.page==0 && !snapshot.candidates.empty() && snapshot.candidates[0].text=="事实");
  command(103);
  check("long English native frame rendered",capture("native-long"));
  command(108);
  check("long English commits full value",snapshot.commit=="intellectual property rights");
  command(104);
  const std::string missingInput=snapshot.input;
  const CSize missingOn=panelSize();
  command(108);
  check("missing definition preserves composition",snapshot.input==missingInput && snapshot.commit.empty() && snapshot.action=="no-definition");
  command(107);const CSize missingOff=panelSize();
  check("missing-definition toggle collapses without candidate change",
    !snapshot.learning && snapshot.input==missingInput && missingOn.cx==missingOff.cx && missingOff.cy<missingOn.cy);
  check("collapsed native frame rendered",capture("native-closed"));
  command(108);
  check("learning off blocks English",snapshot.commit.empty() && snapshot.action=="disabled" && snapshot.input==missingInput);
  const std::string missingChinese=snapshot.candidates.empty()?"":snapshot.candidates[0].text;
  SendMessage(window,WM_CHAR,L' ',0);
  check("learning off still commits Chinese",!missingChinese.empty() && snapshot.commit==missingChinese);
  command(107);command(101);
  check("learning on restores definitions and height",snapshot.learning && panelSize()==initial && snapshot.candidates[0].comment=="apple");
  command(109);
  check("dark theme retains geometry",panelSize()==initial && capture("native-dark"));
  command(109);
  type("pingguoyinhang");refresh(window);engine->Highlight(1);refresh(window);command(108);
  check("partial English action keeps all input",snapshot.input=="pingguoyinhang" && snapshot.commit.empty() && snapshot.action=="partial-composition");
  SendMessage(window,WM_CHAR,L' ',0);SendMessage(window,WM_CHAR,L' ',0);
  check("partial Chinese composition still completes",snapshot.commit=="苹果银行");
  command(101);SendMessage(window,WM_KEYDOWN,VK_BACK,0);
  check("native backspace handler edits composition",snapshot.input=="pinggu");
  bool stable=true;
  for(int i=0;i<20;++i) {
    command(101);command(107);command(107);command(108);
    stable=stable && snapshot.commit=="apple" && snapshot.input.empty();
  }
  check("twenty load-toggle-commit cycles remain consistent",stable);
  report << "],\"dpi\":" << dpi << ",\"normal_width\":" << initial.cx
    << ",\"normal_height\":" << initial.cy << ",\"collapsed_height\":" << missingOff.cy
    << ",\"passed\":" << (all?"true":"false") << '}';
  return all;
}

static bool guardedSelfTest(HWND window) {
  __try {return selfTest(window);}
  __except(reportException(GetExceptionInformation(),WM_APP)) {return false;}
}

static bool measure() {
  Gdiplus::GdiplusStartupInput startup;ULONG_PTR token=0;
  if(Gdiplus::GdiplusStartup(&token,&startup,nullptr)!=Gdiplus::Ok)return false;
  std::ofstream report(root/L"experiments/phase3/results/native-layout.json");
  report << "{\"scope\":\"Actual DirectWrite + Weasel layout at explicit DPI values, not system display switching\",\"cases\":[";
  bool all=true,first=true;
  HDC dc=GetDC(nullptr);
  for(const char* word:{"pingguo","zhishichanquan","zhangxiaoming"}) {
    type(word);readContext();
    for(int dpi:{96,120,144,192})for(bool enabled:{true,false}) {
      weasel::UIStyle s;style(s);if(!enabled)s.comment_text_color=s.hilited_comment_text_color=0;
      auto resources=std::make_shared<weasel::DirectWriteResources>(s,dpi);
      weasel::StudyLayout layout(s,current,status,resources);layout.DoLayout(dc,resources);
      bool valid=!current.cinfo.candies.empty();
      for(int i=0;i<(int)current.cinfo.candies.size();++i) {
        CRect en=layout.GetCandidateCommentRect(i),zh=layout.GetCandidateTextRect(i),hit=layout.GetCandidateRect(i);
        valid=valid && en.bottom<=zh.top && zh.bottom<=hit.bottom && en.left==zh.left;
        if(enabled)valid=valid && hit.PtInRect(en.CenterPoint());
      }
      all=all&&valid;CSize size=layout.GetContentSize();
      if(!first)report << ',';first=false;
      report << "{\"pinyin\":\"" << word << "\",\"dpi\":" << dpi << ",\"learning\":" << (enabled?"true":"false")
        << ",\"width\":" << size.cx << ",\"height\":" << size.cy << ",\"rectangles_valid\":" << (valid?"true":"false") << '}';
    }
  }
  ReleaseDC(nullptr,dc);report << "],\"passed\":" << (all?"true":"false") << '}';
  Gdiplus::GdiplusShutdown(token);return all;
}
int wmain(int argc,wchar_t** argv) {
  wchar_t executable[32768]{};GetModuleFileNameW(nullptr,executable,32768);
  root=argc>1?std::filesystem::absolute(argv[1]):std::filesystem::path(executable).parent_path().parent_path().parent_path().parent_path();
  const std::wstring mode=argc>2?argv[2]:L"";
  automated=mode==L"--smoke" || mode==L"--self-test" || mode==L"--measure";
  auto setDpi=reinterpret_cast<BOOL(WINAPI*)(HANDLE)>(GetProcAddress(GetModuleHandleW(L"user32.dll"),"SetProcessDpiAwarenessContext"));
  if(setDpi)setDpi(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
  if(ATL::_AtlWinModule.cbSize!=sizeof(ATL::_ATL_WIN_MODULE) || ATL::CAtlBaseModule::m_bInitFailed)return 9;
  if(FAILED(_Module.Init(nullptr,GetModuleHandle(nullptr))))return 10;
  if(FAILED(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED)))return 11;
  {
    std::ofstream report(root/L"experiments/phase3/runtime/ui-atl.txt");
    report << "sizeof(_ATL_WIN_MODULE)=" << sizeof(ATL::_ATL_WIN_MODULE)
      << " cbSize=" << ATL::_AtlWinModule.cbSize
      << " init_failed=" << ATL::CAtlBaseModule::m_bInitFailed
      << " lock_count=" << ATL::_AtlWinModule.m_csWindowCreate.m_sec.LockCount << '\n';
  }
  engine=std::make_unique<study::Engine>();
  if(!engine->Open(root))return 5;
  int result=0;
  if(mode==L"--measure") result=measure()?0:6;
  else {
    ui=std::make_unique<weasel::UI>();style(ui->style());
    WNDCLASSW wc{};wc.lpfnWndProc=procedure;wc.hInstance=GetModuleHandle(nullptr);wc.lpszClassName=L"StudyNativeSpike";
    wc.hCursor=LoadCursor(nullptr,IDC_ARROW);wc.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);RegisterClassW(&wc);
    HWND window=CreateWindowW(wc.lpszClassName,L"英语学习输入法 · 原生隔离验证",WS_OVERLAPPEDWINDOW,100,120,700,345,nullptr,nullptr,wc.hInstance,nullptr);
    if(!window)return 7;
    if(mode==L"--self-test") {result=guardedSelfTest(window)?0:12;PostMessage(window,WM_CLOSE,0,0);}
    else if(mode==L"--smoke")PostMessage(window,WM_CLOSE,0,0);
    else {ShowWindow(window,SW_SHOW);UpdateWindow(window);}
    MSG message;while(GetMessage(&message,nullptr,0,0)>0){TranslateMessage(&message);DispatchMessage(&message);}
    ui.reset();
  }
  engine.reset();CoUninitialize();_Module.Term();return result;
}

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <study/windows/WeaselResponse.h>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <vector>

struct Report {
  std::filesystem::path path;
  std::vector<std::pair<std::string, bool>> checks;
  void Check(const char* name, bool passed) {
    checks.emplace_back(name, passed);
    std::ofstream out(path);
    out << "{\"checks\":[";
    for (size_t i=0; i<checks.size(); ++i) {
      if(i) out << ',';
      out << "{\"name\":\"" << checks[i].first << "\",\"passed\":"
          << (checks[i].second ? "true" : "false") << '}';
    }
    out << "]}\n";
    std::cout << (passed ? "PASS " : "FAIL ") << name << std::endl;
    if (!passed) throw std::runtime_error(name);
  }
};
static weasel::UIStyle style;
static auto Read(weasel::Client& client) {
  auto response = study::ReadResponse(client, style);
  if (!response) throw std::runtime_error("Missing response");
  style = response->style;
  return response;
}
static auto Open(weasel::Client& client) {
  bool connected = false;
  for (int i=0; i<300 && !connected; ++i) { connected=client.Connect(); if (!connected) Sleep(10); }
  if (!connected) throw std::runtime_error("Service unavailable");
  client.StartSession();
  return Read(client);
}
static auto Type(weasel::Client& client, const char* text) {
  client.ClearComposition();
  for (; *text; ++text) client.ProcessKeyEvent(weasel::KeyEvent(*text, 0));
  return Read(client);
}
int wmain(int argc, wchar_t** argv) {
  if (argc != 3) return 2;
  Report report{argv[1]};
  try {
    report.Check("x64 frontend executable", sizeof(void*) == 8);
    HMODULE dll = LoadLibraryW(argv[2]);
    report.Check("x64 TSF DLL loads without registration", dll && GetProcAddress(dll, "DllGetClassObject") && GetProcAddress(dll, "DllCanUnloadNow"));
    // Registration exports are deliberately not invoked, including blocked ones.
    if (dll) FreeLibrary(dll);
    std::wstring wire = L"action=commit,ctx,status,study\ncommit=first\nctx.preedit=ni\nstatus.composing=1\nstudy.v1=18446744073709551614,18446744073709551613,18446744073709551612,1,0,snapshot,,\n.\n";
    auto first = study::ParseResponse(wire.data(), static_cast<unsigned>(wire.size()+1), style);
    report.Check("same response preserves uint64 identities", first && first->capability && first->context.preedit.str == L"ni" && first->action.stamp.service == 18446744073709551614ULL && first->action.stamp.version.revision == 18446744073709551612ULL);
    wire.assign(L"action=commit\ncommit=second\n.\n");
    auto second = study::ParseResponse(wire.data(), static_cast<unsigned>(wire.size()+1), style);
    report.Check("owned commits survive shared-buffer overwrite", first->commit == L"first" && second && second->commit == L"second");
    study::CandidateState state;
    state.Accept(first);
    const auto old = state.Generation();
    state.Accept(second);
    study::ActionRequest request;
    report.Check("response without capability clears old action", !state.Current(old) && !state.Request(study::Action::SetLearning, 0, false, request));
    state.Accept(first);
    auto focusToken = state.Generation();
    state.Clear(); state.Accept(first);
    report.Check("same snapshot cannot resurrect an invalidated menu", !state.Current(focusToken));
    wire = L"action=commit\ncommit=unfinished\n";
    report.Check("truncated response cannot become an edit snapshot", !study::ParseResponse(wire.data(), static_cast<unsigned>(wire.size()+1), style));
    wire = L"action=ctx,study\nstudy.v1=1,2,3,1,0,snapshot,,\nstudy.v1=1,2,3,1,0,snapshot,,\n.\n";
    auto duplicate = study::ParseResponse(wire.data(), static_cast<unsigned>(wire.size()+1), style);
    report.Check("duplicate capability disables actions", duplicate && !duplicate->capability);
    weasel::Client client;
    Open(client);
    auto page = Type(client, "nihao");
    state.Accept(page);
    report.Check("x64 frontend reads real candidate and stamp together", page->capability && !page->context.cinfo.empty() && state.Request(study::Action::Inspect, 0, false, request));
    client.StudyAction(request);
    auto inspected = Read(client);
    state.Accept(inspected);
    report.Check("explicit English action uses inspected server target", state.Request(study::Action::CommitEnglish, 0, false, request) && inspected->action.english == "hello");
    const auto menuToken = state.Generation();
    client.ProcessKeyEvent(weasel::KeyEvent('a', 0));
    state.Accept(Read(client));
    report.Check("candidate change invalidates local menu", !state.Current(menuToken));
    auto preserved = Type(client, "nihao");
    state.Accept(preserved);
    state.Request(study::Action::Inspect, 0, false, request);
    client.StudyAction(request); inspected=Read(client);
    state.Accept(inspected); state.Request(study::Action::CommitEnglish, 0, false, request);
    const bool committed = client.StudyAction(request);
    auto english=Read(client);
    client.Echo(); client.FocusIn(); // overwrite transport buffer twice
    report.Check("English standard commit remains owned across later IPC", committed && english->commit == L"hello" && english->action.reason == "english-committed");
    page=Type(client,"nihao"); state.Accept(page);
    state.Request(study::Action::SetLearning,0,false,request);
    client.StudyAction(request); auto disabled=Read(client); state.Accept(disabled);
    report.Check("learning-off response immediately blocks English", !disabled->action.learning && !state.Request(study::Action::CommitEnglish,0,false,request));
    client.ProcessKeyEvent(weasel::KeyEvent(' ',0));
    report.Check("ordinary space still yields Chinese commit", Read(client)->commit == L"你好");
    client.EndSession(); auto reopened=Open(client); state.Accept(reopened);
    report.Check("new session does not restore old menu identity", reopened->action.stamp.version.session != page->action.stamp.version.session && !state.Current(menuToken));
    page=Type(client,"nihao"); state.Accept(page);
    state.Request(study::Action::Inspect,0,false,request);
    client.StudyAction(request); state.Accept(Read(client));
    state.Request(study::Action::CommitEnglish,0,false,request);
    weasel::Client stopper; Open(stopper); stopper.ShutdownServer();
    Sleep(150);
    const bool disconnected = !client.StudyAction(request);
    report.Check("broken connection clears response and active session", disconnected && !study::ReadResponse(client,style) && !client.Echo());
    return 0;
  } catch (const std::exception& e) { std::cerr << e.what() << std::endl; return 1; }
}

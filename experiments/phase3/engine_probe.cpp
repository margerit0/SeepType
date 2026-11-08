// Standalone C API host; no TSF registration, services, or system input settings.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <rime_api.h>
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

static RimeApi* api;
static RimeSessionId session;
static std::string q(const std::string& text) {
  std::ostringstream out; out << '"';
  for(unsigned char c : text) {
    if(c=='"' || c=='\\') out << '\\' << c;
    else if(c<32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(c);
    else out << c;
  }
  out << '"'; return out.str();
}
static std::string safe(const char* value) { return value ? value : ""; }
static std::string property(const char* name) {
  char value[128]={}; api->get_property(session,name,value,sizeof(value)); return value;
}
static void snapshot() {
  RIME_STRUCT(RimeContext, ctx);
  const bool exists=api->get_context(session,&ctx)!=0;
  RIME_STRUCT(RimeCommit, commit);
  const bool committed=api->get_commit(session,&commit)!=0;
  std::cout << "{\"input\":" << q(safe(api->get_input(session)))
    << ",\"commit\":" << q(committed?safe(commit.text):"")
    << ",\"learning\":" << (api->get_option(session,"learning_mode")?"true":"false")
    << ",\"load\":" << q(property("study_load_state"))
    << ",\"action\":" << q(property("study_action"))
    << ",\"page\":" << ctx.menu.page_no
    << ",\"last\":" << (ctx.menu.is_last_page?"true":"false")
    << ",\"selected\":" << ctx.menu.highlighted_candidate_index << ",\"candidates\":[";
  for(int i=0;exists && i<ctx.menu.num_candidates;++i) {
    if(i) std::cout << ',';
    std::cout << "{\"text\":" << q(safe(ctx.menu.candidates[i].text))
      << ",\"comment\":" << q(safe(ctx.menu.candidates[i].comment)) << '}';
  }
  std::cout << "]}" << std::endl;
  if(exists) api->free_context(&ctx);
  if(committed) api->free_commit(&commit);
}
static void type(const std::string& text) {
  for(unsigned char key : text) api->process_key(session,key,0);
}
static void bench(int count, const std::string& input) {
  std::vector<double> times;
  for(int i=-20;i<count;++i) {
    auto start=std::chrono::steady_clock::now();
    api->clear_composition(session); type(input);
    RIME_STRUCT(RimeContext, ctx);
    if(api->get_context(session,&ctx)) api->free_context(&ctx);
    double us=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count();
    if(i>=0) times.push_back(us);
  }
  std::sort(times.begin(),times.end());
  auto percentile=[&](double p){return times[std::min(times.size()-1,size_t(p*(times.size()-1)))];};
  std::cout << "{\"samples\":" << count << ",\"query\":" << q(input) << ",\"unit\":\"us per synthetic composition + first page\",\"p50\":"
    << percentile(.50) << ",\"p95\":" << percentile(.95) << ",\"p99\":" << percentile(.99) << '}' << std::endl;
}
int wmain(int argc,wchar_t** argv) {
  if(argc!=5) {std::cerr << "usage: engine_probe DLL SHARED USER SCHEMA\n";return 2;}
  std::filesystem::path dll=std::filesystem::absolute(argv[1]);
  std::string shared=std::filesystem::absolute(argv[2]).u8string();
  std::string user=std::filesystem::absolute(argv[3]).u8string();
  std::string logs=user+"/logs";
  std::filesystem::create_directories(logs);
  SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  HMODULE module=LoadLibraryExW(dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  if(!module) {std::cerr << "LoadLibrary failed: " << GetLastError() << '\n';return 3;}
  auto entry=reinterpret_cast<RimeApi*(*)()>(GetProcAddress(module,"rime_get_api"));
  if(!entry) return 4;
  api=entry();
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir=shared.c_str();traits.user_data_dir=user.c_str();
  traits.app_name="rime.english-study-spike";
  traits.distribution_name="Isolated study spike";
  traits.distribution_code_name="study-spike";traits.distribution_version="0.1";
  traits.min_log_level=2;traits.log_dir=logs.c_str();
  const char* modules[]={"default","lua",nullptr};traits.modules=modules;
  api->setup(&traits);api->initialize(&traits);
  auto start=std::chrono::steady_clock::now();
  if(api->start_maintenance(True)) api->join_maintenance_thread();
  session=api->create_session();
  std::string schema=std::filesystem::path(argv[4]).u8string();
  if(!session || !api->select_schema(session,schema.c_str())) {
    std::cerr << "Failed to create isolated schema session\n";api->finalize();return 5;
  }
  std::cout << "{\"version\":" << q(api->get_version()) << ",\"lua_module\":"
    << (api->find_module("lua")?"true":"false")
    << ",\"octagram_module\":" << (api->find_module("octagram")?"true":"false")
    << ",\"predict_module\":" << (api->find_module("predict")?"true":"false") << ",\"pointer_bits\":" << sizeof(void*)*8
    << ",\"maintenance_ms\":" << std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count()
    << '}' << std::endl;
  std::string line;
  while(std::getline(std::cin,line)) {
    std::istringstream in(line);std::string command;in>>command;
    if(command=="quit") break;
    if(command=="clear") api->clear_composition(session);
    else if(command=="type") {std::string value;in>>value;type(value);}
    else if(command=="key") {int key=0,mask=0;in>>key>>mask;api->process_key(session,key,mask);}
    else if(command=="option") {std::string name;int value=0;in>>name>>value;api->set_option(session,name.c_str(),value);}
    else if(command=="user_learning") {int value=1;in>>value;api->set_property(session,"study_user_learning",value?"1":"0");}
    else if(command=="schema") {std::string name;in>>name;api->clear_composition(session);api->select_schema(session,name.c_str());}
    else if(command=="highlight") {size_t index=0;in>>index;if(RIME_API_AVAILABLE(api,highlight_candidate_on_current_page))api->highlight_candidate_on_current_page(session,index);}
    else if(command=="choose") {size_t index=0;in>>index;api->select_candidate_on_current_page(session,index);}
    else if(command=="forget") {size_t index=0;in>>index;if(RIME_API_AVAILABLE(api,delete_candidate_on_current_page))api->delete_candidate_on_current_page(session,index);}
    else if(command=="bench") {int count=0;std::string input;in>>count>>input;bench(std::clamp(count,1,2000),input.empty()?"pingguo":input);continue;}
    snapshot();
  }
  api->destroy_session(session);api->finalize();FreeLibrary(module);return 0;
}

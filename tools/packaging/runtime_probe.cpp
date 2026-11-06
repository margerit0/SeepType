// Packaging-only checks: exercise relocated data/runtime paths, not a rerun of
// the existing TSF, UI, menu, animation or full lexicon acceptance suites.
#include "stdafx.h"
#include <study/windows/WeaselResponse.h>
#include <study/windows/ProductRuntime.h>
#include <fstream>
#include <iostream>
#include <stdexcept>

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return 2;
  std::vector<std::pair<std::string, bool>> checks;
  auto check = [&](const std::string& name, bool ok) {
    checks.emplace_back(name, ok);
    std::ofstream output{std::filesystem::path(argv[1])};
    output << "{\"checks\":[";
    for (size_t i = 0; i < checks.size(); ++i) {
      if (i) output << ',';
      output << "{\"name\":\"" << checks[i].first << "\",\"passed\":" << (checks[i].second ? "true" : "false") << '}';
    }
    output << "],\"registration_executed\":false,\"physical_input_executed\":false}\n";
    std::cout << (ok ? "PASS " : "FAIL ") << name << std::endl;
    if (!ok) throw std::runtime_error(name);
  };
  try {
    const auto pipe = study::ProductPipeName();
    check("product pipe has a separate developer identity", pipe.find(L"StudyIME-v1-S-") != std::wstring::npos && pipe.find(L"-dev-") != std::wstring::npos);
    weasel::Client client;
    if (!client.Connect()) throw std::runtime_error("Packaged service unavailable");
    client.StartSession();
    weasel::UIStyle style;
    auto read = [&] {
      auto response = study::ReadResponse(client, style);
      if (!response) throw std::runtime_error("Incomplete packaged Rime response");
      style = response->style;
      return response;
    };
    auto first = read();
    check("only the packaged study schema is active", first->status.schema_id == L"study");
    struct Sample { const char* pinyin; const wchar_t* chinese; const char* english; };
    const Sample samples[] = {{"nihao", L"你好", "hello"}, {"xiexie", L"谢谢", "thank you"},
        {"pingguo", L"苹果", "apple"}, {"mingtian", L"明天", "tomorrow"}, {"yiyuan", L"医院", "hospital"}};
    for (const auto& sample : samples) {
      auto type = [&] {
        client.ClearComposition();
        std::shared_ptr<const study::WeaselResponse> response;
        for (const char* key = sample.pinyin; *key; ++key) { client.ProcessKeyEvent(*key); response = read(); }
        return response;
      };
      auto response = type();
      unsigned index = 0;
      const auto& candidates = response->context.cinfo.candies;
      while (index < candidates.size() && candidates[index].str != sample.chinese) ++index;
      check(std::string("relocated Chinese data: ") + sample.pinyin, index < candidates.size());
      study::ActionRequest inspect{study::Action::Inspect, response->action.stamp, index, false};
      bool ok = client.StudyAction(inspect);
      response = read();
      check(std::string("packaged preview Lua meaning: ") + sample.pinyin, ok && response->action.english == sample.english);
      study::ActionRequest commit{study::Action::CommitEnglish, response->action.stamp, index, false};
      ok = client.StudyAction(commit);
      response = read();
      const std::wstring english(sample.english, sample.english + strlen(sample.english));
      check(std::string("packaged English commit: ") + sample.pinyin, ok && response->commit == english);
      response = type();
      ok = client.SelectCandidateOnCurrentPage(index);
      response = read();
      check(std::string("packaged Chinese commit: ") + sample.pinyin, ok && response->commit == sample.chinese);
    }
    client.EndSession();
    client.Disconnect();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    return 1;
  }
}

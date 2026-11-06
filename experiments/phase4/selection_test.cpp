#include "stdafx.h"
#include <study/windows/WeaselResponse.h>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <stdexcept>

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return 2;
  std::vector<std::pair<std::string, bool>> checks;
  auto check = [&](const char* name, bool passed) {
    checks.emplace_back(name, passed);
    std::ofstream out{std::filesystem::path(argv[1])}; out << "{\"checks\":[";
    for (size_t i = 0; i < checks.size(); ++i) {
      if (i) out << ',';
      out << "{\"name\":\"" << checks[i].first << "\",\"passed\":" << (checks[i].second ? "true" : "false") << '}';
    }
    out << "]}\n";
    std::cout << (passed ? "PASS " : "FAIL ") << name << std::endl;
    if (!passed) throw std::runtime_error(name);
  };
  try {
    weasel::Client client; bool connected = false;
    for (int i = 0; i < 300 && !connected; ++i) { connected = client.Connect(); if (!connected) Sleep(10); }
    if (!connected) throw std::runtime_error("Isolated service unavailable");
    client.StartSession();
    weasel::UIStyle style;
    auto read = [&] {
      auto response = study::ReadResponse(client, style);
      if (!response) throw std::runtime_error("Expected complete ordinary response");
      style = response->style; return response;
    };
    read();
    auto type = [&](const char* text) {
      client.ClearComposition();
      std::shared_ptr<const study::WeaselResponse> response;
      for (; *text; ++text) { client.ProcessKeyEvent(static_cast<int>(*text)); response = read(); }
      return response;
    };
    auto response = type("nihao");
    const bool selected = client.SelectCandidateOnCurrentPage(0); auto commit = read();
    check("ordinary selection returns Chinese commit and capability in the same response",
        selected && commit->commit == L"你好" && commit->capability && !commit->status.composing);
    client.ProcessKeyEvent('n'); response = read();
    check("next key does not replay the selected Chinese commit", response->commit.empty() && response->status.composing);
    response = type("pingguo");
    const study::ActionRequest old{study::Action::Inspect, response->action.stamp, 0, false};
    client.CommitComposition();  // Deliberately leave an application commit pending.
    const bool inspected = client.StudyAction(old); response = read();
    check("rejected inspection leaves a pending Chinese commit untouched", !inspected && response->commit.empty());
    const bool rejected = client.SelectCandidateOnCurrentPage(9999); response = read();
    check("rejected ordinary selection does not consume the pending commit", !rejected && response->commit.empty());
    client.ProcessKeyEvent('n'); response = read();
    check("pending Chinese remains available to the next normal response", response->commit == L"苹果" && response->status.composing);
    response = type("shishi"); client.ChangePage(false); read(); client.HighlightCandidateOnCurrentPage(1); response = read();
    const auto before = response;
    study::ActionRequest off{study::Action::SetLearning, response->action.stamp, 0, false};
    const bool disabled = client.StudyAction(off); response = read();
    check("learning toggle preserves Rime page selection input and commit ownership", disabled && !response->action.learning && response->commit.empty() &&
        response->context.cinfo.currentPage == before->context.cinfo.currentPage && response->context.cinfo.highlighted == before->context.cinfo.highlighted &&
        response->context.preedit.str == before->context.preedit.str);
    study::ActionRequest inspect{study::Action::Inspect, response->action.stamp, 1, false};
    client.StudyAction(inspect); response = read();
    check("disabled learning is also enforced by authoritative Lua inspection", response->action.reason == "disabled" && response->action.english.empty());
    client.EndSession(); client.ShutdownServer();
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << std::endl; return 1; }
}

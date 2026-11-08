#pragma once

#include "stdafx.h"
#include <study/windows/WeaselResponse.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

struct Checks {
  std::filesystem::path path;
  std::vector<std::pair<std::string, bool>> items;
  void Check(const std::string& name, bool passed) {
    items.emplace_back(name, passed);
    std::ofstream out(path);
    out << "{\"checks\":[";
    for (size_t i = 0; i < items.size(); ++i) {
      if (i) out << ',';
      out << "{\"name\":\"" << items[i].first << "\",\"passed\":"
          << (items[i].second ? "true" : "false") << '}';
    }
    out << "],\"registration_executed\":false,\"physical_input_executed\":false}\n";
    std::cout << (passed ? "PASS " : "FAIL ") << name << std::endl;
    if (!passed) throw std::runtime_error(name);
  }
};

struct Connection {
  weasel::Client client;
  weasel::UIStyle style;
  std::shared_ptr<const study::WeaselResponse> response;
  Connection() {
    if (!client.Connect()) throw std::runtime_error("Product service unavailable");
    client.StartSession();
    Read();
  }
  ~Connection() { client.EndSession(); client.Disconnect(); }
  void Read() {
    response = study::ReadResponse(client, style);
    if (!response || !response->capability) throw std::runtime_error("Incomplete product response");
    style = response->style;
  }
  void Key(int key, int mask = 0) {
    client.ProcessKeyEvent(weasel::KeyEvent(key, mask));
    Read();
  }
  void Type(const char* input) {
    client.ClearComposition();
    for (auto p = input; *p; ++p) Key(*p);
  }
  std::pair<unsigned, unsigned> FindCurrent(const wchar_t* word) {
    for (unsigned page = 0; page < 80; ++page) {
      const auto& items = response->context.cinfo.candies;
      for (unsigned i = 0; i < items.size(); ++i)
        if (items[i].str == word) return {page * 5 + i + 1, i};
      const bool changed = client.ChangePage(false);
      Read();
      if (!changed) break;
    }
    throw std::runtime_error("Expected candidate not found");
  }
  std::pair<unsigned, unsigned> Find(const char* input, const wchar_t* word) {
    Type(input);
    return FindCurrent(word);
  }
  bool Action(study::Action action, unsigned index = 0, bool enabled = false) {
    study::ActionRequest request{action, response->action.stamp, index, enabled};
    const bool accepted = client.StudyAction(request);
    Read();
    return accepted;
  }
  void Choose(unsigned index) {
    if (!client.SelectCandidateOnCurrentPage(index)) throw std::runtime_error("Selection failed");
    Read();
  }
};

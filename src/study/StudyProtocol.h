#pragma once

#include "SessionActions.h"
#include <string_view>

namespace study {

enum class Action { Inspect, CommitEnglish, SetLearning };

struct ActionStamp {
  std::uint64_t service = 0;
  VersionStamp version;
};

// No candidate text is accepted from the client.
struct ActionRequest {
  Action action = Action::Inspect;
  ActionStamp stamp;
  std::uint32_t index = 0;
  bool enabled = false;
};

struct ActionState {
  ActionStamp stamp;
  bool learning = false;
  std::uint32_t index = 0;
  std::string reason = "unavailable";
  std::string chinese;
  std::string english;
  bool Available() const { return reason == "ready" && !english.empty(); }
};

constexpr std::size_t kMaxRequestChars = 192;
constexpr std::size_t kMaxDefinitionBytes = 2048;

std::wstring EncodeRequest(const ActionRequest& request);
bool DecodeRequest(std::wstring_view text, ActionRequest& request);
std::string EncodeState(const ActionState& state);
// Parse the study line in a complete ordinary Weasel response. Old servers
// have no such line: absence, duplicates and malformed fields fail closed.
bool DecodeState(std::wstring_view response, ActionState& state);

}  // namespace study

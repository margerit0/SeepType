#include "WeaselResponse.h"
#include <ResponseParser.h>

namespace study {
std::shared_ptr<const WeaselResponse> ParseResponse(
    wchar_t* buffer, unsigned length, const weasel::UIStyle& previous_style) {
  if (!buffer || length > 32768) return {};
  const auto size = wcsnlen(buffer, length);
  if (!size || size == length) return {};
  const std::wstring_view wire(buffer, size);
  if (wire.size() < 2 || wire.substr(wire.size() - 2) != L".\n") return {};
  auto result = std::make_shared<WeaselResponse>();
  result->style = previous_style;  // styles are deliberately sent only on change
  try {
    weasel::ResponseParser parser(&result->commit, &result->context,
        &result->status, &result->config, &result->style);
    if (!parser(buffer, length)) return {};
  } catch (...) { return {}; }
  result->capability = DecodeState(wire, result->action);
  return result;
}

std::shared_ptr<const WeaselResponse> ReadResponse(
    weasel::Client& client, const weasel::UIStyle& previous_style) {
  std::shared_ptr<const WeaselResponse> result;
  client.GetResponseData([&](wchar_t* buffer, unsigned length) {
    result = ParseResponse(buffer, length, previous_style);
    return !!result;
  });
  return result;
}

bool CandidateState::Request(Action action, unsigned index, bool enabled,
                             ActionRequest& out) const {
  if (!response_ || !response_->capability) return false;
  const auto& state = response_->action;
  if (action != Action::SetLearning &&
      (!response_->status.composing || index >= response_->context.cinfo.candies.size()))
    return false;
  if (action == Action::CommitEnglish &&
      (!state.Available() || index != state.index)) return false;
  out = {action, state.stamp, action == Action::SetLearning ? 0 : index, enabled};
  return true;
}
}  // namespace study

#pragma once
#include <WeaselIPC.h>
#include <WeaselIPCData.h>
#include <memory>

namespace study {
// Owned response: the pipe buffer may be overwritten immediately after Read.
struct WeaselResponse {
  std::wstring commit;
  weasel::Context context;
  weasel::Status status;
  weasel::Config config;
  weasel::UIStyle style;
  ActionState action;
  bool capability = false;
};
std::shared_ptr<const WeaselResponse> ReadResponse(
    weasel::Client& client, const weasel::UIStyle& previous_style);
std::shared_ptr<const WeaselResponse> ParseResponse(
    wchar_t* buffer, unsigned length, const weasel::UIStyle& previous_style);

// Apartment-thread state. Every response or local invalidation kills menu tokens.
class CandidateState {
 public:
  void Clear() { ++generation_; response_.reset(); }
  void Accept(std::shared_ptr<const WeaselResponse> response) {
    Clear(); response_ = std::move(response);
  }
  std::uint64_t Generation() const { return generation_; }
  bool Current(std::uint64_t token) const { return token == generation_ && response_; }
  std::shared_ptr<const WeaselResponse> Response() const { return response_; }
  bool Request(Action action, unsigned index, bool enabled, ActionRequest& out) const;
 private:
  std::uint64_t generation_ = 1;
  std::shared_ptr<const WeaselResponse> response_;
};
}  // namespace study

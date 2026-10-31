#include <rime_api.h>
#include "RimeSession.h"
#include <vector>

namespace study {

struct RimeSession::Impl {
  RimeApi* api;
  RimeSessionId session;
  SessionVersion version;

  struct Context {
    std::string input;
    std::size_t caret = 0;
    int page = 0;
    int highlighted = -1;
    std::vector<std::string> candidates;
  };

  bool Ready() const {
    return api && session && api->find_session(session) &&
        RIME_API_AVAILABLE(api, get_caret_pos) &&
        RIME_API_AVAILABLE(api, highlight_candidate_on_current_page);
  }

  std::string Property(const char* name) const {
    char buffer[4096]{};
    if (!api->get_property(session, name, buffer, sizeof(buffer))) return {};
    buffer[sizeof(buffer) - 1] = 0;
    return buffer;
  }

  bool Request(const char* request) {
    if (Property("study_protocol") != "1") return false;
    for (const auto name : {"study_response", "study_target_text",
                            "study_target_english", "study_target_reason"})
      api->set_property(session, name, "");
    api->set_property(session, "study_request", request);
    const bool handled = api->process_key(session, 0, 0) != 0;
    api->set_property(session, "study_request", "");
    return handled && Property("study_response") == request;
  }

  Context Read() const {
    Context result;
    const char* input = api->get_input(session);
    result.input = input ? input : "";
    result.caret = api->get_caret_pos(session);
    RIME_STRUCT(RimeContext, context);
    if (api->get_context(session, &context)) {
      result.page = context.menu.page_no;
      result.highlighted = context.menu.highlighted_candidate_index;
      for (int i = 0; i < context.menu.num_candidates; ++i) {
        const char* text = context.menu.candidates[i].text;
        result.candidates.emplace_back(text ? text : "");
      }
      api->free_context(&context);
    }
    // Deliberately never call get_commit here.
    return result;
  }
};

RimeSession::RimeSession(void* api, std::uintptr_t session)
    : impl_(std::make_unique<Impl>()) {
  impl_->api = static_cast<RimeApi*>(api);
  impl_->session = session;
}
RimeSession::~RimeSession() = default;

VersionStamp RimeSession::Version() const { return impl_->version.Current(); }
void RimeSession::Invalidate() { impl_->version.Invalidate(); }
bool RimeSession::Learning() const {
  return impl_->Ready() && impl_->api->get_option(impl_->session, "learning_mode");
}
void RimeSession::SetLearning(bool enabled) {
  Invalidate();
  if (impl_->Ready())
    impl_->api->set_option(impl_->session, "learning_mode", enabled);
}

EnglishTarget RimeSession::Inspect(std::size_t index) {
  auto& s = *impl_;
  EnglishTarget target;
  target.version = Version();
  target.index = index;
  if (!s.Ready()) { target.reason = "unavailable"; return target; }
  auto context = s.Read();
  if (index >= context.candidates.size()) return target;
  if (index != static_cast<std::size_t>(context.highlighted)) {
    Invalidate();
    if (!s.api->highlight_candidate_on_current_page(s.session, index)) {
      target.reason = "unavailable";
      target.version = Version();
      return target;
    }
  }
  const bool inspected = s.Request("inspect-v1");
  context = s.Read();
  target.version = Version();
  target.page = context.page;
  target.caret = context.caret;
  target.input = context.input;
  if (!inspected || index >= context.candidates.size() ||
      context.highlighted != static_cast<int>(index)) {
    target.reason = "unavailable";
    return target;
  }
  target.chinese = s.Property("study_target_text");
  target.english = s.Property("study_target_english");
  target.reason = s.Property("study_target_reason");
  if (target.reason.empty() || target.chinese != context.candidates[index])
    target.reason = "unavailable";
  return target;
}

bool RimeSession::Commit(const EnglishTarget& target) {
  auto& s = *impl_;
  if (!s.Ready() || !s.version.Matches(target.version)) return false;
  const auto context = s.Read();
  if (target.index >= context.candidates.size() || target.page != context.page ||
      target.input != context.input || target.caret != context.caret ||
      static_cast<int>(target.index) != context.highlighted ||
      target.chinese != context.candidates[target.index]) return false;
  const auto current = Inspect(target.index);
  if (!current.Available() || !target.Available() ||
      current.english != target.english) return false;
  // Invalidate before dispatch. Retransmitting a request cannot commit twice.
  Invalidate();
  return s.Request("commit-v1") &&
      s.Property("study_action") == "english-committed";
}

}  // namespace study

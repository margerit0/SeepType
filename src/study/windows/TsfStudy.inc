// Included by the generated WeaselTSF/EditSession.cpp, in its COM apartment.
#include <study/windows/EnglishMenu.h>

// TrackPopupMenu pumps messages. A short-lived thread timer closes its menu if
// the service disappears, even when the user is not pressing another key.
class StudyMenuWatch {
 public:
  explicit StudyMenuWatch(std::function<void()> check) : check_(std::move(check)) {
    id_ = SetTimer(nullptr, 0, 250, Tick);
    if (id_) watches()[id_] = this;
  }
  ~StudyMenuWatch() { Stop(); }
  void Stop() {
    if (id_) { KillTimer(nullptr, id_); watches().erase(id_); id_ = 0; }
  }
  bool Started() const { return id_ != 0; }
 private:
  static std::map<UINT_PTR, StudyMenuWatch*>& watches() {
    static thread_local std::map<UINT_PTR, StudyMenuWatch*> instances;
    return instances;
  }
  static void CALLBACK Tick(HWND, UINT, UINT_PTR id, DWORD) {
    auto found = watches().find(id);
    if (found != watches().end()) found->second->check_();
  }
  UINT_PTR id_ = 0;
  std::function<void()> check_;
};

class StudyResponseEditSession : public CEditSession {
 public:
  StudyResponseEditSession(WeaselTSF* tsf, com_ptr<ITfContext> context,
      std::shared_ptr<const study::WeaselResponse> response,
      std::uint64_t epoch, std::uint64_t serial)
      : CEditSession(tsf, context), response_(std::move(response)),
        epoch_(epoch), serial_(serial) {}
  STDMETHODIMP DoEditSession(TfEditCookie cookie) override {
    return _pTextService->_ApplyResponse(cookie, _pContext, response_, epoch_, serial_);
  }
 private:
  std::shared_ptr<const study::WeaselResponse> response_;
  std::uint64_t epoch_, serial_;
};

void WeaselTSF::_InvalidateStudy() {
  ++_studySerial;  // pending edits may commit, but may not republish old UI
  _studyCandidates.Clear();
  if (_studyMenuOpen) EndMenu();
}

HRESULT WeaselTSF::_RunEdit(com_ptr<ITfContext> context, ITfEditSession* session,
                           DWORD flags, HRESULT* result) {
  if (_studyApplying && context == _pEditSessionContext) {
    *result = session->DoEditSession(_studyCookie);
    return S_OK;
  }
  return context->RequestEditSession(_tfClientId, session, flags, result);
}

void WeaselTSF::_QueueResponse(com_ptr<ITfContext> context,
    std::shared_ptr<const study::WeaselResponse> response) {
  _InvalidateStudy();
  if (!context || !response) return;
  const auto serial = ++_studySerial;
  com_ptr<StudyResponseEditSession> edit;
  edit.Attach(new StudyResponseEditSession(this, context, response, _studyEpoch, serial));
  HRESULT result = E_FAIL;
  const HRESULT requested = context->RequestEditSession(_tfClientId, edit,
      TF_ES_ASYNCDONTCARE | TF_ES_READWRITE, &result);
  _async_edit = result == TF_S_ASYNC;
  if (FAILED(requested) || FAILED(result)) _InvalidateStudy();
}

STDAPI WeaselTSF::DoEditSession(TfEditCookie) {
  // Legacy shared-buffer entry is deliberately inert.
  return E_UNEXPECTED;
}

HRESULT WeaselTSF::_ApplyResponse(TfEditCookie cookie, com_ptr<ITfContext> document,
    std::shared_ptr<const study::WeaselResponse> response,
    std::uint64_t epoch, std::uint64_t serial) {
  if (epoch != _studyEpoch || !_pThreadMgr || _studyApplying) return S_FALSE;
  com_ptr<ITfDocumentMgr> focused;
  com_ptr<ITfContext> top;
  if (FAILED(_pThreadMgr->GetFocus(&focused)) || !focused ||
      FAILED(focused->GetTop(&top)) || top != document) return S_FALSE;
  _pEditSessionContext = document;
  _studyApplying = true;
  _studyCookie = cookie;
  struct Reset { bool& flag; ~Reset() { flag = false; } } reset{_studyApplying};
  _status = response->status;
  _cand->style() = response->style;
  const auto& config = response->config;
  const auto& commit = response->commit;
  auto context = std::make_shared<weasel::Context>(response->context);
  _UpdateLanguageBar(_status);
  if (!commit.empty()) {
    if (!_IsComposing())
      _StartComposition(document, _fCUASWorkaroundEnabled && !config.inline_preedit);
    _InsertText(document, commit);
    _EndComposition(document, false);
    _committed = TRUE;
  } else _committed = FALSE;
  if (_status.composing && !_IsComposing())
    _StartComposition(document, _fCUASWorkaroundEnabled && !config.inline_preedit);
  else if (!_status.composing && _IsComposing())
    _EndComposition(document, true);
  if (_IsComposing() && config.inline_preedit) _ShowInlinePreedit(document, context);
  if (serial == _studySerial && epoch == _studyEpoch) {
    _studyCandidates.Accept(response);
    _UpdateCompositionWindow(document);
    _UpdateUI(*context, _status);
  }
  return S_OK;
}

bool WeaselTSF::_StudyAction(study::Action action, unsigned index, bool enabled) {
  study::ActionRequest request;
  if (!_pEditSessionContext || !_studyCandidates.Request(action, index, enabled, request))
    return false;
  // Do not reconnect/replay an action. A new session needs a fresh key response.
  if (!m_client.Echo()) { ++_studyEpoch; _InvalidateStudy(); return false; }
  _InvalidateStudy();
  const bool accepted = m_client.StudyAction(request);
  auto response = study::ReadResponse(m_client, _cand->style());
  if (!response) { ++_studyEpoch; return false; }
  _QueueResponse(_pEditSessionContext, response);
  return accepted;
}

void WeaselTSF::_StudyMenu(unsigned index, HWND, POINT position) {
  com_ptr<WeaselTSF> keepAlive(this);
  study::ActionRequest request;
  if (_studyMenuOpen || !_pEditSessionContext ||
      !_studyCandidates.Request(study::Action::Inspect, index, false, request)) return;
  if (!m_client.Echo()) { ++_studyEpoch; _InvalidateStudy(); return; }
  _InvalidateStudy();
  const bool accepted = m_client.StudyAction(request);
  auto response = study::ReadResponse(m_client, _cand->style());
  if (!response) { ++_studyEpoch; return; }
  if (!accepted || !response->capability) {
    _QueueResponse(_pEditSessionContext, response); return;
  }
  // Inspection cannot contain an application commit. Hold the response until
  // the menu exits, outside any TSF write lock. Nested input/focus closes it.
  _studyCandidates.Accept(response);
  _UpdateUI(response->context, response->status);
  const auto token = _studyCandidates.Generation();
  study::EnglishTarget target;
  target.chinese = response->action.chinese;
  target.english = response->action.english;
  target.reason = response->action.reason;
  StudyMenuWatch watch([this, token] {
    if (!_studyCandidates.Current(token) || !m_client.Echo()) {
      ++_studyEpoch;
      _InvalidateStudy();
    }
  });
  if (!watch.Started()) { _QueueResponse(_pEditSessionContext, response); return; }
  _studyMenuOpen = true;
  const UINT command = study::ShowEnglishMenu(_GetFocusedContextWindow(), position, target);
  watch.Stop();
  _studyMenuOpen = false;
  if (!_studyCandidates.Current(token)) return;
  if (command == study::kInputEnglish)
    _StudyAction(study::Action::CommitEnglish, index);
  else
    _QueueResponse(_pEditSessionContext, response);
}

bool WeaselTSF::_StudyKey(WPARAM key, LPARAM info, BOOL* eaten) {
  const bool release = (static_cast<ULONG_PTR>(info) & (1ULL << 31)) != 0;
  const bool control = (GetKeyState(VK_CONTROL) & 0x8000) != 0;
  const bool shift = (GetKeyState(VK_SHIFT) & 0x8000) != 0;
  const bool alt = (GetKeyState(VK_MENU) & 0x8000) != 0;
  const bool commit = key == VK_RETURN && control && shift && !alt;
  const bool menu = key == VK_APPS || (key == VK_F10 && shift && !control && !alt);
  if (!commit && !menu) return false;
  auto response = _studyCandidates.Response();
  if (!response || !response->capability || response->context.cinfo.empty()) return false;
  _studyKeyHandled = true;
  *eaten = TRUE;
  if (release) return true;
  const unsigned index = response->context.cinfo.highlighted;
  if (menu) {
    POINT point{}; GetCursorPos(&point);
    _StudyMenu(index, _GetFocusedContextWindow(), point);
  } else {
    study::ActionRequest request;
    if (!_studyCandidates.Request(study::Action::Inspect, index, false, request)) return true;
    const auto epoch = _studyEpoch;
    _InvalidateStudy();
    const bool accepted = m_client.StudyAction(request);
    auto inspected = study::ReadResponse(m_client, _cand->style());
    if (!inspected || epoch != _studyEpoch) return true;
    study::CandidateState target;
    target.Accept(inspected);
    if (accepted && target.Request(study::Action::CommitEnglish, index, false, request)) {
      m_client.StudyAction(request);
      auto committed = study::ReadResponse(m_client, _cand->style());
      _QueueResponse(_pEditSessionContext, committed);
    } else _QueueResponse(_pEditSessionContext, inspected);
  }
  return true;
}

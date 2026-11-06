"""TSF overlay additions; called by prepare-weasel.py with its checked replacer."""
def prepare(source, replace):
    h = 'WeaselTSF/WeaselTSF.h'
    replace(h, '#include <WeaselIPCData.h>', '#include <WeaselIPCData.h>\n#include <study/windows/WeaselResponse.h>')
    replace(h, '  /* IPC */', '''  void _InvalidateStudy();
  bool _StudyAction(study::Action action, unsigned index, bool enabled = false);
  void _StudyMenu(unsigned index, HWND owner, POINT position);
  bool _StudyKey(WPARAM key, LPARAM info, BOOL* eaten);
  void _QueueResponse(com_ptr<ITfContext> context,
                      std::shared_ptr<const study::WeaselResponse> response);
  HRESULT _ApplyResponse(TfEditCookie cookie, com_ptr<ITfContext> context,
      std::shared_ptr<const study::WeaselResponse> response,
      std::uint64_t epoch, std::uint64_t serial);
  HRESULT _RunEdit(com_ptr<ITfContext> context, ITfEditSession* session,
                   DWORD flags, HRESULT* result);
  /* IPC */''')
    replace(h, '  /* IME status */', '''  study::CandidateState _studyCandidates;
  std::uint64_t _studyEpoch = 1, _studySerial = 0;
  bool _studyMenuOpen = false, _studyApplying = false;
  TfEditCookie _studyCookie = 0;
  /* IME status */''')
    c = 'WeaselTSF/Composition.cpp'
    old = source(c)
    begin = old.index('void WeaselTSF::_UpdateComposition(')
    end = old.index('/* Composition State */', begin)
    replace(c, old[begin:end], '''void WeaselTSF::_UpdateComposition(com_ptr<ITfContext> pContext) {
  auto response = study::ReadResponse(m_client, _cand->style());
  if (!response) { _InvalidateStudy(); return; }
  _QueueResponse(pContext, std::move(response));
}

''')
    # Existing composition helpers run under the already-granted cookie during
    # response application. No nested asynchronous insertion of a stale commit.
    replace(c, 'pContext->RequestEditSession(_tfClientId,', '_RunEdit(pContext,', count=5)
    replace(c, 'void WeaselTSF::_AbortComposition(bool clear) {', 'void WeaselTSF::_AbortComposition(bool clear) {\n  ++_studyEpoch;\n  _InvalidateStudy();')
    replace(c, '  _AbortComposition();\n  return S_OK;', '  if (!_studyApplying && _pComposition == pComposition) _AbortComposition();\n  return S_OK;')
    # A deferred termination owns the OLD composition. Detach it immediately so
    # focus can create a new document's composition; its eventual callback may
    # not finalize a newer composition belonging to that other document.
    replace(h, 'void _FinalizeComposition();', 'void _FinalizeComposition(ITfComposition* expected);')
    replace(c, '_pTextService->_FinalizeComposition();', '_pTextService->_FinalizeComposition(_pComposition);')
    replace(c, 'void WeaselTSF::_FinalizeComposition() {\n  _pComposition = nullptr;', 'void WeaselTSF::_FinalizeComposition(ITfComposition* expected) {\n  if (_pComposition == expected) _pComposition = nullptr;')
    replace(c, '  _cand->EndUI();\n  if ((pEditSession', '  _cand->EndUI();\n  auto ending = _pComposition;\n  if ((pEditSession')
    replace(c, 'this, pContext, _pComposition, clear)) != NULL) {', 'this, pContext, ending, clear)) != NULL) {\n    _pComposition = nullptr;')
    # Clear attributes using the captured composition, never mutable service state.
    replace(c, '  _pTextService->_ClearCompositionDisplayAttributes(ec, _pContext);', '''  com_ptr<ITfProperty> attribute;
  com_ptr<ITfRange> endingRange;
  if (SUCCEEDED(_pComposition->GetRange(&endingRange)) &&
      SUCCEEDED(_pContext->GetProperty(GUID_PROP_ATTRIBUTE, &attribute)))
    attribute->Clear(ec, endingRange);''')
    replace(c, '  ITfRange* pCompositionRange;', '  com_ptr<ITfRange> pCompositionRange;')
    replace('WeaselTSF/TextEditSink.cpp', '  BOOL fSelectionChanged;', '  if (pContext != _pEditSessionContext) return S_OK;\n  BOOL fSelectionChanged;')
    # Bind each request to its own COM context and immutable pipe response.
    e = 'WeaselTSF/EditSession.cpp'
    replace(e, source(e), '''#include "stdafx.h"
#include "WeaselTSF.h"
#include "CandidateList.h"
#include "EditSession.h"
#include <study/windows/TsfStudy.inc>
''')
    k = 'WeaselTSF/KeyEventSink.cpp'
    replace(k, '  weasel::KeyEvent ke;', '''  if (_StudyKey(wParam, lParam, pfEaten)) { _studyKeyHandled = true; return; }
  _InvalidateStudy();
  weasel::KeyEvent ke;''')
    replace(k, '  else {\n    m_client.FocusOut();', '  else {\n    ++_studyEpoch;\n    _InvalidateStudy();\n    m_client.FocusOut();')
    replace(k, '    if (!_async_edit)\n      _UpdateComposition(pContext);', '    _UpdateComposition(pContext);')
    replace(k, '    if (!keyCountToSimulate)\n      *pfEaten = (BOOL)m_client.ProcessKeyEvent(ke);', '    if (!keyCountToSimulate) {\n      _studyKeyHandled = false;\n      *pfEaten = (BOOL)m_client.ProcessKeyEvent(ke);\n    }')
    # An explicit action already captured/scheduled its response. Do not read it
    # twice in the outer key handler.
    replace(h, 'bool _studyMenuOpen = false, _studyApplying = false;', 'bool _studyMenuOpen = false, _studyApplying = false, _studyKeyHandled = false;')
    replace(k, '  // when _IsKeyboardDisabled', '  _studyKeyHandled = true;\n  // when _IsKeyboardDisabled')
    replace(k, '  _UpdateComposition(pContext);', '  if (!_studyKeyHandled) _UpdateComposition(pContext);', count=4)
    # UI callbacks read their response immediately instead of injecting VK_SELECT.
    ca = 'WeaselTSF/CandidateList.cpp'
    data = source(ca)
    a = data.index('  // simulate a VK_SELECT')
    b = data.index('\n}', a)
    replace(ca, data[a:b], '  _UpdateComposition(_pEditSessionContext);')
    for signature in ['void WeaselTSF::_SelectCandidateOnCurrentPage(size_t index) {',
                      'void WeaselTSF::_HandleMouseHoverEvent(const size_t index) {']:
        replace(ca, signature, signature + '\n  _InvalidateStudy();')
    replace(ca, '  // from scrolling event', '  _InvalidateStudy();\n  // from scrolling event')
    replace(ca, 'void WeaselTSF::_HideUI() {', 'void WeaselTSF::_HideUI() {\n  _InvalidateStudy();')
    replace(ca, 'void CCandidateList::StartUI() {', '''void CCandidateList::StartUI() {
  _ui->studyMenu = [this](unsigned index, HWND owner, POINT position) {
    _tsf->_StudyMenu(index, owner, position);
  };''')
    t = 'WeaselTSF/WeaselTSF.cpp'
    # Unregistered host calls ITfKeyEventSink directly; Windows refuses global
    # keystroke sink ownership for a TIP absent from the installed profiles.
    replace(t, '  if (!_InitKeyEventSink())\n    goto ExitError;', '#ifndef WEASEL_STUDY_ISOLATED\n  if (!_InitKeyEventSink())\n    goto ExitError;\n#endif')
    replace(t, '  _UninitKeyEventSink();', '#ifndef WEASEL_STUDY_ISOLATED\n  _UninitKeyEventSink();\n#endif')
    # The isolated DLL is activated directly by a text host. Do not publish a
    # language bar or alter the user's keyboard compartments/profile settings.
    replace(t, '  _InitDisplayAttributeGuidAtom();', '  _InitDisplayAttributeGuidAtom();\n#ifndef WEASEL_STUDY_ISOLATED')
    replace(t, '  if (!_InitThreadFocusSink())', '#endif\n  if (!_InitThreadFocusSink())')
    replace(t, '  _UninitPreservedKey();', '  _UninitPreservedKey();\n  _UninitThreadFocusSink();')
    replace(t, 'STDAPI WeaselTSF::Deactivate() {', 'STDAPI WeaselTSF::Deactivate() {\n  if (!_pThreadMgr) return S_OK;\n  _AbortComposition();')
    replace(t, '  _cand = new CCandidateList(this);', '  _cand.Attach(new CCandidateList(this));')
    replace(t, '  _activateFlags = dwFlags;', '  if (!_cand) _cand.Attach(new CCandidateList(this));\n  _activateFlags = dwFlags;')
    replace(t, '  _pThreadMgr = NULL;', '''  _cand->EndUI();
  _cand->DestroyAll();
  _cand.Release();
  _pEditSessionContext.Release();
  _pThreadMgr = NULL;''')
    replace(t, '  _cand->DestroyAll();\n\n  return S_OK;', '  return S_OK;')
    replace(t, 'void WeaselTSF::_UninitThreadFocusSink() {', 'void WeaselTSF::_UninitThreadFocusSink() {\n  if (_dwThreadFocusSinkCookie == TF_INVALID_COOKIE) return;')
    replace(t, '  if (FAILED(pSource->UnadviseSink(_dwThreadFocusSinkCookie)))\n    return;', '  pSource->UnadviseSink(_dwThreadFocusSinkCookie);\n  _dwThreadFocusSinkCookie = TF_INVALID_COOKIE;')
    replace(t, '  _AbortComposition();\n  return S_OK;', '  m_client.FocusOut();\n  _AbortComposition();\n  return S_OK;')
    replace(t, '    weasel::ResponseParser parser(NULL, NULL, &_status, NULL, &_cand->style());\n    bool ok = m_client.GetResponseData(std::ref(parser));\n    if (ok)\n      _UpdateLanguageBar(_status);', '    auto response = study::ReadResponse(m_client, _cand->style());\n    if (response) _QueueResponse(_pTextEditSinkContext, response);\n    else _InvalidateStudy();')
    replace(t, 'void WeaselTSF::_Reconnect() {', 'void WeaselTSF::_Reconnect() {\n  ++_studyEpoch;\n  _InvalidateStudy();')
    # No detached thread touching a COM apartment or launching an installed service.
    data = source(t)
    a = data.index('static unsigned int retry = 0;')
    replace(t, data[a:], '''bool WeaselTSF::_EnsureServerConnected() {
  if (m_client.Echo()) return true;
  _Reconnect();
  return m_client.Echo();
}
''')
    f = 'WeaselTSF/ThreadMgrEventSink.cpp'
    replace(f, '  _InitTextEditSink(pDocMgrFocus);', '''  if (pDocMgrFocus != pDocMgrPrevFocus) {
    _AbortComposition();
    m_client.FocusOut();
  }
  _InitTextEditSink(pDocMgrFocus);''')
    replace(f, 'STDAPI WeaselTSF::OnPopContext(ITfContext* pContext) {', '''STDAPI WeaselTSF::OnPopContext(ITfContext* pContext) {
  ++_studyEpoch;
  _InvalidateStudy();''')
    # Right-click uses the actual candidate hit rectangles; ordinary left click
    # and both lines still use the unchanged Chinese selection callback.
    u = 'include/WeaselUI.h'
    replace(u, '  // 创建输入法界面', '  std::function<void(unsigned, HWND, POINT)> studyMenu;\n\n  // 创建输入法界面')
    p = 'WeaselUI/WeaselPanel.h'
    replace(p, '  MESSAGE_HANDLER(WM_CREATE, OnCreate)', '  MESSAGE_HANDLER(WM_CONTEXTMENU, OnStudyMenu)\n  MESSAGE_HANDLER(WM_CREATE, OnCreate)')
    replace(p, '  LRESULT OnCreate(', '  LRESULT OnStudyMenu(UINT, WPARAM, LPARAM, BOOL&);\n  LRESULT OnCreate(')
    p = 'WeaselUI/WeaselPanel.cpp'
    # Access the UI callback through the UI reference retained in the panel.
    replace('WeaselUI/WeaselPanel.h', '  weasel::Context& m_ctx;', '  weasel::UI& m_studyUI;\n  weasel::Context& m_ctx;')
    replace(p, '      m_ctx(ui.ctx()),', '      m_studyUI(ui), m_ctx(ui.ctx()),')
    data = source(p)
    source_text = '''
LRESULT WeaselPanel::OnStudyMenu(UINT, WPARAM, LPARAM lParam, BOOL&) {
  if (!m_layout || !m_studyUI.studyMenu) return 0;
  POINT screen{GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam)};
  unsigned index = static_cast<unsigned>(m_ctx.cinfo.highlighted);
  if (screen.x == -1 && screen.y == -1) {
    RECT rc{}; GetWindowRect(&rc); screen = {rc.left, rc.bottom};
  } else {
    POINT local = screen; ScreenToClient(&local);
    bool found = false;
    for (unsigned i = 0; i < m_ctx.cinfo.candies.size() && i < MAX_CANDIDATES_COUNT; ++i) {
      auto rect = m_layout->GetCandidateRect(i);
      if (m_istorepos) rect.OffsetRect(0, m_offsetys[i]);
      rect.InflateRect(DPI_SCALE(m_style.hilite_padding_x), DPI_SCALE(m_style.hilite_padding_y));
      if (rect.PtInRect(local)) { index = i; found = true; break; }
    }
    if (!found) return 0;
  }
  auto callback = m_studyUI.studyMenu;
  callback(index, m_hWnd, screen);
  return 0;
}
'''
    replace(p, data, data + source_text)

    server = 'WeaselTSF/Server.cpp'
    for name in ['DllRegisterServer', 'DllUnregisterServer']:
        data = source(server)
        start = data.index('STDAPI ' + name + '()')
        brace = data.index('{', start)
        replace(server, data[start:brace+1], data[start:brace+1] + '\n#ifdef WEASEL_STUDY_ISOLATED\n  return E_ACCESSDENIED;\n#endif')

    replace('WeaselTSF/WeaselTSF.rc', '#include "afxres.h"', '#include <winres.h>')

    replace('WeaselTSF/WeaselTSF.rc', '#include <winres.h>', '#include <winres.h>\n#define VERSION_MAJOR 0\n#define VERSION_MINOR 17\n#define VERSION_PATCH 4\n#define FILE_VERSION "0.17.4-study-isolated"\n#define PRODUCT_VERSION 0.17.4-study-isolated')

    replace('include/WeaselUtility.h', '  const auto logs = WeaselUserDataPath() / L"logs";', '#ifdef WEASEL_STUDY_TSF\n  const auto logs = fs::temp_directory_path() / L"StudyIme-Phase4-TSF";\n#else\n  const auto logs = WeaselUserDataPath() / L"logs";\n#endif')

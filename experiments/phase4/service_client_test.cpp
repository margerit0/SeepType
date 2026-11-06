// Real Weasel clients communicating with a separate Weasel server process.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <WeaselIPC.h>
#include <ResponseParser.h>
#include <PipeChannel.h>
#include <study/StudyProtocol.h>
#include <atomic>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>

struct Reply {
  bool parsed = false;
  bool capability = false;
  std::wstring commit;
  weasel::Context context;
  weasel::Status status;
  weasel::Config config;
  weasel::UIStyle style;
  study::ActionState study;
};

static Reply Parse(wchar_t* buffer, DWORD length) {
  Reply reply;
  const auto size = wcsnlen(buffer, length);
  if (!size || size == length) return reply;
  weasel::ResponseParser parser(&reply.commit, &reply.context, &reply.status,
                                 &reply.config, &reply.style);
  reply.parsed = parser(buffer, length);
  reply.capability = study::DecodeState(std::wstring_view(buffer, size), reply.study);
  return reply;
}

static Reply Read(weasel::Client& client) {
  Reply reply;
  client.GetResponseData([&](wchar_t* buffer, DWORD length) {
    reply = Parse(buffer, length); return reply.parsed;
  });
  return reply;
}

static Reply Open(weasel::Client& client) {
  bool connected = false;
  for (int i = 0; i < 300 && !connected; ++i) {
    connected = client.Connect();
    if (!connected) Sleep(10);
  }
  if (!connected) throw std::runtime_error("Isolated Weasel pipe unavailable");
  client.StartSession();
  auto reply = Read(client);
  if (!reply.capability) throw std::runtime_error("Missing study capability in actual server response");
  return reply;
}

static Reply Key(weasel::Client& client, int code, int mask = 0) {
  client.ProcessKeyEvent(weasel::KeyEvent(code, mask));
  return Read(client);
}

static Reply Type(weasel::Client& client, const char* input) {
  client.ClearComposition();
  Reply reply;
  for (; *input; ++input) reply = Key(client, static_cast<unsigned char>(*input));
  if (!reply.capability) throw std::runtime_error("Key response lost study capability");
  return reply;
}

static study::ActionRequest Request(const Reply& reply, study::Action action,
                                   std::uint32_t index = 0, bool enabled = false) {
  if (!reply.capability) throw std::runtime_error("Cannot act without a current server stamp");
  return {action, reply.study.stamp, index, enabled};
}

struct Result { bool accepted; Reply reply; };
static Result Act(weasel::Client& client, const study::ActionRequest& request) {
  const bool accepted = client.StudyAction(request);
  return {accepted, Read(client)};
}
static Result Inspect(weasel::Client& client, const Reply& reply, std::uint32_t index = 0) {
  return Act(client, Request(reply, study::Action::Inspect, index));
}

static bool Has(const Reply& reply, const wchar_t* chinese) {
  for (const auto& candidate : reply.context.cinfo.candies)
    if (candidate.str == chinese) return true;
  return false;
}

struct Report {
  std::filesystem::path path;
  std::vector<std::pair<std::string, bool>> checks;
  bool passed = true;
  void Check(const char* name, bool ok) {
    passed &= ok;
    checks.emplace_back(name, ok);
    std::ofstream output(path);
    output << "{\"passed\":" << (passed ? "true" : "false") << ",\"checks\":[";
    for (size_t i = 0; i < checks.size(); ++i) {
      if (i) output << ',';
      output << "{\"name\":\"" << checks[i].first << "\",\"passed\":"
             << (checks[i].second ? "true" : "false") << '}';
    }
    output << "]}\n";
    std::cout << (ok ? "PASS " : "FAIL ") << name << std::endl;
  }
};

static void RestartTest(weasel::Client& client, const Reply& initial,
                        const std::filesystem::path& ticket, Report& report) {
  std::wifstream input(ticket);
  std::wstring wire((std::istreambuf_iterator<wchar_t>(input)), {});
  study::ActionRequest old;
  if (!study::DecodeRequest(wire, old)) throw std::runtime_error("Invalid saved test ticket");
  auto current = Type(client, "pingguo");
  auto menu = Inspect(client, current);
  auto rejected = Act(client, old);
  report.Check("service restart rejects a ticket from the previous process",
      menu.reply.study.Available() && old.stamp.service != initial.study.stamp.service &&
      !rejected.accepted && rejected.reply.commit.empty() &&
      rejected.reply.study.reason == "stale-candidate" && Has(rejected.reply, L"苹果"));
  menu = Inspect(client, rejected.reply);
  auto fresh = Act(client, Request(menu.reply, study::Action::CommitEnglish));
  report.Check("a fresh ticket still commits after the service restart",
      fresh.accepted && fresh.reply.commit == L"apple");
}

static void PartialTest(weasel::Client& client, Report& report) {
  auto current = Type(client, "pingguoy");
  std::uint32_t apple = 255;
  for (size_t i = 0; i < current.context.cinfo.candies.size(); ++i)
    if (current.context.cinfo.candies[i].str == L"苹果") apple = static_cast<std::uint32_t>(i);
  auto menu = Inspect(client, current, apple);
  auto result = Act(client, Request(menu.reply, study::Action::CommitEnglish, apple));
  const bool passed = apple != 255 && menu.reply.study.reason == "partial-composition" &&
      !result.accepted && result.reply.commit.empty() &&
      result.reply.context.preedit.str == menu.reply.context.preedit.str;
  // Inspecting a nonfirst candidate may legitimately update the composition's
  // displayed selection. Compare before/after the attempted commit action.
  if (!passed) {
    std::cerr << "Partial input diagnostic: index=" << apple
      << " reason=" << menu.reply.study.reason << " accepted=" << result.accepted
      << " before=" << wtou8(current.context.preedit.str)
      << " inspected=" << wtou8(menu.reply.context.preedit.str)
      << " after=" << wtou8(result.reply.context.preedit.str) << std::endl;
  }
  report.Check("partial composition cannot lose remaining pinyin through IPC", passed);
}

int wmain(int argc, wchar_t** argv) {
  if (argc < 3) return 2;
  Report report{argv[1]};
  try {
    weasel::Client client;
    auto current = Open(client);
    if (std::wstring(argv[2]) == L"--dispatch") {
      current = Type(client, "pingguo");
      report.Check("window-dispatched Rime response keeps candidates and capability together",
          current.parsed && current.capability && Has(current, L"苹果"));
      auto inspected = Inspect(client, current);
      auto ticket = Request(inspected.reply, study::Action::CommitEnglish);
      auto committed = Act(client, ticket);
      report.Check("window-dispatched explicit English action uses the normal commit response",
          inspected.accepted && committed.accepted && committed.reply.commit == L"apple");
      auto duplicate = Act(client, ticket);
      report.Check("window dispatch does not replay an already completed action",
          !duplicate.accepted && duplicate.reply.commit.empty());
      current = Type(client, "pingguo");
      auto disabled = Act(client, Request(current, study::Action::SetLearning, 0, false));
      auto enabled = Act(client, Request(disabled.reply, study::Action::SetLearning, 0, true));
      report.Check("learning option notifications remain coherent on the window owner",
          disabled.accepted && !disabled.reply.study.learning && enabled.accepted && enabled.reply.study.learning &&
          disabled.reply.context.preedit.str == enabled.reply.context.preedit.str);
      auto menu = Inspect(client, enabled.reply);
      ticket = Request(menu.reply, study::Action::CommitEnglish);
      client.FocusOut(); client.FocusIn();
      auto rejected = Act(client, ticket);
      report.Check("focus change still invalidates a menu across window dispatch",
          !rejected.accepted && rejected.reply.commit.empty() && Has(rejected.reply, L"苹果"));
      client.EndSession(); client.ShutdownServer();
      return report.passed ? 0 : 1;
    }
    if (std::wstring(argv[2]) == L"--partial") {
      PartialTest(client, report);
      client.EndSession(); client.ShutdownServer();
      return report.passed ? 0 : 1;
    }
    if (argc == 4 && std::wstring(argv[2]) == L"--restart") {
      RestartTest(client, current, argv[3], report);
      client.EndSession(); client.ShutdownServer();
      return report.passed ? 0 : 1;
    }

    current = Type(client, "pingguo");
    report.Check("ordinary Weasel responses carry candidates and the study capability",
        current.parsed && current.capability && Has(current, L"苹果") && current.study.learning);
    auto menu = Inspect(client, current);
    report.Check("IPC inspection preserves composition and exposes the complete definition",
        menu.accepted && menu.reply.study.Available() && menu.reply.study.chinese == "苹果" &&
        menu.reply.study.english == "apple" && menu.reply.commit.empty() &&
        menu.reply.context.preedit.str == current.context.preedit.str);
    const auto ticket = Request(menu.reply, study::Action::CommitEnglish);
    auto result = Act(client, ticket);
    report.Check("IPC English commit reaches the standard Weasel commit response exactly once",
        result.accepted && result.reply.commit == L"apple" && result.reply.context.empty());
    result = Act(client, ticket);
    report.Check("retransmitting a consumed ticket cannot duplicate committed English",
        !result.accepted && result.reply.commit.empty() && result.reply.study.reason == "stale-candidate");
    current = Key(client, 'p');
    report.Check("typing continues through IPC after an English commit",
        current.commit.empty() && !current.context.preedit.empty());

    current = Type(client, "pingguo"); menu = Inspect(client, current);
    auto old = Request(menu.reply, study::Action::CommitEnglish);
    const auto edited = Key(client, ibus::BackSpace);
    result = Act(client, old);
    report.Check("editing pinyin invalidates an outstanding IPC ticket",
        !result.accepted && result.reply.commit.empty() &&
        result.reply.context.preedit.str == edited.context.preedit.str &&
        result.reply.study.reason == "stale-candidate");

    current = Type(client, "shishi"); menu = Inspect(client, current);
    old = Request(menu.reply, study::Action::CommitEnglish);
    client.ChangePage(false); current = Read(client);
    result = Act(client, old);
    auto page = Inspect(client, result.reply);
    report.Check("paging rejects the previous ticket and binds the current page",
        !result.accepted && result.reply.commit.empty() && current.context.cinfo.currentPage == 1 &&
        page.reply.study.chinese == "适时" && page.reply.study.english == "at the right time");
    result = Act(client, Request(page.reply, study::Action::CommitEnglish));
    report.Check("current-page IPC action commits that page's full English",
        result.accepted && result.reply.commit == L"at the right time");

    current = Type(client, "shishi"); menu = Inspect(client, current);
    old = Request(menu.reply, study::Action::CommitEnglish);
    client.ChangePage(false); Read(client);
    client.ChangePage(true); Read(client);
    result = Act(client, old);
    report.Check("returning to the original page does not revive an old IPC ticket",
        !result.accepted && result.reply.commit.empty() && result.reply.context.cinfo.currentPage == 0);
    current = Type(client, "shishi"); menu = Inspect(client, current);
    old = Request(menu.reply, study::Action::CommitEnglish);
    client.HighlightCandidateOnCurrentPage(2); Read(client);
    result = Act(client, old);
    auto selected = Inspect(client, result.reply, 2);
    auto selectedCommit = Act(client, Request(selected.reply, study::Action::CommitEnglish, 2));
    report.Check("selection changes invalidate the old ticket and preserve the selected target",
        !result.accepted && selectedCommit.accepted && selectedCommit.reply.commit == L"give it a try");

    current = Type(client, "zhishichanquan"); menu = Inspect(client, current);
    result = Act(client, Request(menu.reply, study::Action::CommitEnglish));
    report.Check("long English survives IPC serialization without an ellipsis",
        menu.reply.study.english == "intellectual property rights" &&
        result.accepted && result.reply.commit == L"intellectual property rights");

    current = Type(client, "pingguo"); menu = Inspect(client, current);
    old = Request(menu.reply, study::Action::CommitEnglish);
    auto off = Act(client, Request(menu.reply, study::Action::SetLearning, 0, false));
    auto disabled = Inspect(client, off.reply);
    auto noCommit = Act(client, Request(disabled.reply, study::Action::CommitEnglish));
    report.Check("learning-off IPC action disables English without changing Chinese composition",
        off.accepted && !off.reply.study.learning && disabled.reply.study.reason == "disabled" &&
        !noCommit.accepted && noCommit.reply.commit.empty() && Has(noCommit.reply, L"苹果"));
    auto on = Act(client, Request(noCommit.reply, study::Action::SetLearning, 0, true));
    result = Act(client, old);
    report.Check("turning learning back on does not reactivate an old ticket",
        on.accepted && on.reply.study.learning && !result.accepted && result.reply.commit.empty());

    current = Type(client, "zhangxiaoming"); menu = Inspect(client, current);
    result = Act(client, Request(menu.reply, study::Action::CommitEnglish));
    report.Check("missing definitions are unavailable through the actual IPC action",
        menu.reply.study.reason == "no-definition" && !result.accepted &&
        result.reply.commit.empty() && Has(result.reply, L"张小明"));

    PartialTest(client, report);

    current = Type(client, "pingguo"); menu = Inspect(client, current);
    old = Request(menu.reply, study::Action::CommitEnglish);
    client.FocusOut(); result = Act(client, old);
    report.Check("an inactive session cannot accept an old English ticket",
        !result.accepted && result.reply.commit.empty() && result.reply.study.reason == "inactive-session");
    client.FocusIn(); result = Act(client, old);
    report.Check("focus restoration requires a fresh ticket",
        !result.accepted && result.reply.commit.empty() && result.reply.study.reason == "stale-candidate");

    menu = Inspect(client, result.reply);
    old = Request(menu.reply, study::Action::CommitEnglish);
    weasel::Client other;
    Open(other);
    auto inactive = Act(client, old);
    auto crossSession = Act(other, old);
    report.Check("another client cannot use a ticket from the first session",
        !inactive.accepted && inactive.reply.study.reason == "inactive-session" &&
        !crossSession.accepted && crossSession.reply.study.reason == "stale-candidate" &&
        inactive.reply.commit.empty() && crossSession.reply.commit.empty());
    other.EndSession(); other.Disconnect();
    client.EndSession(); client.StartSession(); current = Read(client);
    result = Act(client, old);
    report.Check("recreating a session rejects its predecessor's ticket",
        current.capability && !result.accepted && result.reply.commit.empty() &&
        current.study.stamp.version.session != old.stamp.version.session);

    current = Type(client, "pingguo"); menu = Inspect(client, current);
    old = Request(menu.reply, study::Action::Inspect);
    client.CommitComposition();
    result = Act(client, old);
    auto empty = Inspect(client, result.reply);
    current = Key(client, 'n');
    report.Check("inspection never drains a pending Chinese commit from the application",
        result.reply.commit.empty() && empty.reply.commit.empty() &&
        current.commit == L"苹果" && !current.context.preedit.empty());
    current = Type(client, "pingguo");
    current = Key(client, ibus::Return, 5);
    report.Check("keyboard and IPC English actions share the same Lua commit behavior",
        current.commit == L"apple" && current.context.empty());

    // Send malformed requests over the real transport, bypassing client-side
    // validation. A header-only frame must not reuse the last body or reply.
    weasel::PipeChannel<weasel::PipeMessage> raw(weasel::GetPipeName());
    if (!raw.Connect()) throw std::runtime_error("Raw test connection unavailable");
    raw << L"action=session\nsession.client_app=study-protocol-test.exe\nsession.client_type=tsf\n.\n";
    weasel::PipeMessage message{WEASEL_IPC_START_SESSION, 0, 0};
    const DWORD rawSession = raw.Transact(message);
    Reply rawReply;
    auto rawRead = [&]() {
      weasel::ResponseHandler parser = [&](wchar_t* b, DWORD n) { rawReply = Parse(b, n); return true; };
      raw.HandleResponseData(parser);
    };
    rawRead();
    const auto valid = study::EncodeRequest(Request(rawReply, study::Action::Inspect));
    std::vector<std::wstring> malformed = {
      L"study.v2=inspect,1,1,1,0,0\n.\n",
      L"study.v1=commit,1,1,18446744073709551616,0,0\n.\n",
      L"study.v1=commit,1,1,1,-1,0\n.\n",
      L"study.v1=commit,1,1,1,0,0,caller supplied English\n.\n",
      valid.substr(0, valid.size() - 1),
      std::wstring(2048, L'x')
    };
    bool malformedRejected = rawSession != 0;
    for (const auto& wire : malformed) {
      raw << wire; message = {WEASEL_IPC_STUDY_ACTION, 0, rawSession};
      malformedRejected &= raw.Transact(message) == 0;
      rawRead(); malformedRejected &= !rawReply.capability && rawReply.commit.empty();
    }
    report.Check("malformed and unsupported IPC frames cannot trigger English actions", malformedRejected);
    raw << valid; message = {WEASEL_IPC_STUDY_ACTION, 0, rawSession};
    const bool validAccepted = raw.Transact(message) != 0;
    rawRead(); const bool hadReply = rawReply.capability;
    const bool headerOnlyRejected = raw.Transact(message) == 0;
    rawRead();
    report.Check("header-only IPC frames cannot replay a previous request body or response",
        validAccepted && hadReply && headerOnlyRejected && !rawReply.capability && rawReply.commit.empty());
    message = {WEASEL_IPC_END_SESSION, 0, rawSession}; raw.Transact(message); raw.Disconnect();

    study::ActionState decoded;
    const auto stateWire = study::EncodeState(current.study);
    const std::wstring stateLine(stateWire.begin(), stateWire.end());
    report.Check("client decoder rejects missing capabilities duplicate states and incomplete replies",
        !study::DecodeState(L"action=noop\n.\n", decoded) &&
        !study::DecodeState(stateLine + stateLine + L".\n", decoded) &&
        !study::DecodeState(stateLine, decoded));

    client.EndSession();
    std::atomic<bool> concurrentOk{true};
    auto worker = [&](const char* pinyin, const wchar_t* expected) {
      try {
        weasel::Client connection; Open(connection);
        for (int i = 0; i < 16; ++i) {
          auto reply = Type(connection, pinyin);
          if (!Has(reply, expected) || !reply.commit.empty() || !reply.capability)
            concurrentOk = false;
        }
        connection.EndSession(); connection.Disconnect();
      } catch (...) { concurrentOk = false; }
    };
    std::thread first(worker, "pingguo", L"苹果");
    std::thread second(worker, "nihao", L"你好");
    first.join(); second.join();
    report.Check("concurrent pipe connections keep their request and response bodies isolated", concurrentOk);

    client.StartSession(); Read(client);
    current = Type(client, "pingguo"); menu = Inspect(client, current);
    std::wofstream saved(argv[2]);
    saved << study::EncodeRequest(Request(menu.reply, study::Action::CommitEnglish));
    saved.close();
    client.EndSession(); client.ShutdownServer();
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    report.Check("test completed without a transport or setup failure", false);
    return 2;
  }
  return report.passed ? 0 : 1;
}

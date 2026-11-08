// Synthetic real-product IPC. Every mutable path must be an isolated dev root.
#include "ipc_probe.h"
#include <study/windows/ProductRuntime.h>
#include <study/windows/UiPreferences.h>

static bool SchemaIs(const Connection& connection, study::InputScheme scheme) {
  const std::string id = study::InputSchemaId(scheme);
  return connection.response->status.schema_id == std::wstring(id.begin(), id.end());
}

int wmain(int argc, wchar_t** argv) {
  if (argc != 3) return 2;
  Checks checks{argv[1]};
  try {
    using namespace study;
    checks.Check("double pinyin probe requires isolated product data",
        ProductPipeName().find(L"-dev-") != std::wstring::npos);
    const std::wstring mode = argv[2];
    const auto settings = PreferencesPath();
    auto saveScheme = [&](InputScheme scheme) {
      auto value = LoadPreferences(settings);
      value.inputScheme = scheme;
      if (!SavePreferences(settings, value)) throw std::runtime_error("Cannot save input scheme");
    };
    Connection c;

    if (mode == L"restart") {
      checks.Check("saved Flypy scheme is selected on service restart",
          LoadPreferences(settings).inputScheme == InputScheme::Flypy && SchemaIs(c, InputScheme::Flypy));
      checks.Check("learned word survives a service restart in Flypy", c.Find("uiui", L"事实").first == 1);
      saveScheme(InputScheme::FullPinyin);
      checks.Check("restarted full pinyin sees the same learned word", c.Find("shishi", L"事实").first == 1 && SchemaIs(c, InputScheme::FullPinyin));
      saveScheme(InputScheme::NaturalDoublePinyin);
      checks.Check("restarted natural double pinyin sees the same learned word", c.Find("uiui", L"事实").first == 1 && SchemaIs(c, InputScheme::NaturalDoublePinyin));
      return 0;
    }

    if (mode == L"upgrade") {
      const auto legacy = LoadPreferences(settings);
      checks.Check("legacy preferences default to full pinyin and retain other choices",
          legacy.inputScheme == InputScheme::FullPinyin && !legacy.learning && legacy.largeText &&
          legacy.theme == Theme::Dark && legacy.shortcut == EnglishShortcut::AltEnter && SchemaIs(c, InputScheme::FullPinyin));
      checks.Check("upgraded full pinyin retains an old learned word", c.Find("shijian", L"实践").first == 1);
      saveScheme(InputScheme::NaturalDoublePinyin);
      checks.Check("old single-schema user data can select natural double pinyin",
          c.Find("uijm", L"实践").first == 1 && SchemaIs(c, InputScheme::NaturalDoublePinyin));
      saveScheme(InputScheme::Flypy);
      checks.Check("old single-schema user data can select Flypy with the same learning",
          c.Find("uijm", L"实践").first == 1 && SchemaIs(c, InputScheme::Flypy));
      checks.Check("scheme changes preserve the disabled English preference",
          !c.response->action.learning && c.response->context.cinfo.comments[0].str.empty());
      return 0;
    }
    if (mode != L"exercise") return 2;

    checks.Check("fresh product sessions keep full pinyin as default", SchemaIs(c, InputScheme::FullPinyin));
    const auto preferenceCases = settings.parent_path() / L"scheme-preferences.ini";
    UiPreferences prefs;
    prefs.learning = false; prefs.userLearning = false; prefs.largeText = true;
    prefs.reduceMotion = true; prefs.theme = Theme::Dark; prefs.shortcut = EnglishShortcut::AltEnter;
    for (const auto scheme : {InputScheme::FullPinyin, InputScheme::NaturalDoublePinyin, InputScheme::Flypy}) {
      prefs.inputScheme = scheme;
      checks.Check(std::string("all preferences round-trip with ") + InputSchemaId(scheme),
          SavePreferences(preferenceCases, prefs) && LoadPreferences(preferenceCases) == prefs);
    }
    {
      std::ofstream file(preferenceCases);
      file << "version=1\nlearning=0\nuser_learning=0\nlarge_text=1\ntheme=dark\ninput_scheme=unknown\n";
    }
    const auto unknown = LoadPreferences(preferenceCases);
    checks.Check("unknown input schemes fall back to full pinyin without losing other settings",
        unknown.inputScheme == InputScheme::FullPinyin && !unknown.learning && !unknown.userLearning && unknown.largeText && unknown.theme == Theme::Dark);

    c.Type("nihao"); c.Key(' ');
    checks.Check("existing full pinyin still commits Chinese", c.response->commit == L"你好");
    saveScheme(InputScheme::NaturalDoublePinyin);
    auto found = c.Find("nihk", L"你好");
    checks.Check("an existing idle session picks up natural double pinyin on its next key", SchemaIs(c, InputScheme::NaturalDoublePinyin));
    c.Choose(found.second);
    checks.Check("natural double pinyin mouse selection submits Chinese", c.response->commit == L"你好");

    // Saving a scheme while input is active must not reinterpret that input.
    c.Type("nihk");
    const auto preedit = c.response->context.preedit.str;
    saveScheme(InputScheme::Flypy);
    c.Action(Action::Inspect, 0);
    checks.Check("saving a new scheme leaves the current candidates and preedit intact",
        SchemaIs(c, InputScheme::NaturalDoublePinyin) && c.response->context.preedit.str == preedit && c.response->commit.empty());
    c.Key(' ');
    checks.Check("space completes an existing composition with its original scheme",
        c.response->commit == L"你好" && SchemaIs(c, InputScheme::NaturalDoublePinyin));
    found = c.Find("nihc", L"你好");
    checks.Check("the next composition uses Flypy", SchemaIs(c, InputScheme::Flypy));
    c.Key('1' + found.second);
    checks.Check("Flypy number selection submits Chinese", c.response->commit == L"你好");

    saveScheme(InputScheme::NaturalDoublePinyin);
    found = c.Find("nihk", L"你好");
    saveScheme(InputScheme::Flypy);
    c.Choose(found.second);
    checks.Check("a mouse click after saving a scheme still completes the original composition",
        c.response->commit == L"你好" && SchemaIs(c, InputScheme::NaturalDoublePinyin));

    // The TSF CommitComposition path leaves its commit for the next response.
    saveScheme(InputScheme::NaturalDoublePinyin);
    c.Type("nihk"); c.client.CommitComposition();
    saveScheme(InputScheme::Flypy);
    c.Key(0);
    checks.Check("a schema switch does not consume a pending application commit",
        c.response->commit == L"你好" && SchemaIs(c, InputScheme::Flypy));

    c.Type("nihc"); c.Key(0xff1b);
    saveScheme(InputScheme::NaturalDoublePinyin);
    c.Type("nihk"); c.Key(' ');
    checks.Check("cancelling input permits the next scheme without committing cancelled text", c.response->commit == L"你好");

    // Each existing composition keeps its own engine until it is finished.
    c.Type("nihk");
    saveScheme(InputScheme::Flypy);
    {
      Connection other;
      checks.Check("a new concurrent session immediately uses the saved scheme", SchemaIs(other, InputScheme::Flypy));
      other.Type("nihc"); other.Key(' ');
      checks.Check("a concurrent Flypy session submits Chinese", other.response->commit == L"你好");
      c.Key(' ');
      checks.Check("an older concurrent composition retains natural double pinyin",
          c.response->commit == L"你好" && SchemaIs(c, InputScheme::NaturalDoublePinyin));
    }
    c.Type("nihc");
    checks.Check("the older session adopts Flypy after finishing its composition", SchemaIs(c, InputScheme::Flypy));

    for (const auto scheme : {InputScheme::NaturalDoublePinyin, InputScheme::Flypy}) {
      saveScheme(scheme);
      const std::string label = InputSchemaId(scheme);
      const char* hello = scheme == InputScheme::Flypy ? "nihc" : "nihk";
      const std::string segmented = std::string(hello) + "ma";
      auto partial = c.Find(segmented.c_str(), L"你好");
      c.Action(Action::Inspect, partial.second);
      const auto composition = c.response->context.preedit.str;
      const bool accepted = c.Action(Action::CommitEnglish, partial.second);
      checks.Check(label + " rejects English for a partial candidate without dropping the suffix",
          !accepted && c.response->action.reason == "partial-composition" &&
          c.response->commit.empty() && c.response->context.preedit.str == composition);
      c.Choose(partial.second);
      checks.Check(label + " partial Chinese selection keeps the remaining input", c.response->commit.empty() && c.response->status.composing);
      partial = c.FindCurrent(L"吗"); c.Choose(partial.second);
      checks.Check(label + " segmented selection commits the entire phrase", c.response->commit == L"你好吗");

      c.Type("uiui");
      const auto first = c.response->context.cinfo.candies;
      const bool paged = c.client.ChangePage(false); c.Read();
      checks.Check(label + " pages through candidates", paged && c.response->context.cinfo.currentPage == 1);
      const bool returned = c.client.ChangePage(true); c.Read();
      const auto& again = c.response->context.cinfo.candies;
      checks.Check(label + " returns to the first candidate page", returned &&
          c.response->context.cinfo.currentPage == 0 && again.size() == first.size() &&
          std::equal(again.begin(), again.end(), first.begin(),
              [](const weasel::Text& a, const weasel::Text& b) { return a.str == b.str; }));
      const bool pastBeginning = c.client.ChangePage(true); c.Read();
      checks.Check(label + " rejects paging before the first page", !pastBeginning && c.response->context.cinfo.currentPage == 0);

      found = c.Find(hello, L"你好");
      c.Action(Action::Inspect, found.second);
      checks.Check(label + " provides the existing complete English definition", c.response->action.english == "hello");
      const ActionRequest ticket{Action::CommitEnglish, c.response->action.stamp, found.second, false};
      const bool committed = c.client.StudyAction(ticket); c.Read();
      checks.Check(label + " explicitly submits English", committed && c.response->commit == L"hello" && !c.response->status.composing);
      const bool repeated = c.client.StudyAction(ticket); c.Read();
      checks.Check(label + " rejects a repeated English action", !repeated && c.response->commit.empty());
    }

    found = c.Find("nihc", L"你好"); c.Action(Action::Inspect, found.second);
    const ActionRequest stale{Action::CommitEnglish, c.response->action.stamp, found.second, false};
    saveScheme(InputScheme::NaturalDoublePinyin); c.Type("nihk");
    const bool staleAccepted = c.client.StudyAction(stale); c.Read();
    checks.Check("changing schemes rejects an old English candidate ticket", !staleAccepted && c.response->commit.empty());
    c.Action(Action::SetLearning, 0, false);
    saveScheme(InputScheme::Flypy); c.Type("nihc");
    checks.Check("switching schemes preserves the independent English display state", !c.response->action.learning && c.response->context.cinfo.comments[0].str.empty());
    c.Action(Action::SetLearning, 0, true);

    // All layouts use cedict_study.userdb; ranks and forgetting cross layouts.
    saveScheme(InputScheme::FullPinyin);
    const auto baseRank = c.Find("shishi", L"事实").first;
    checks.Check("cross-layout learning fixture has a non-first built-in rank", baseRank > 1);
    saveScheme(InputScheme::NaturalDoublePinyin);
    found = c.Find("uiui", L"事实"); c.Choose(found.second);
    checks.Check("natural double pinyin learns an ordinary Chinese choice", c.response->commit == L"事实" && c.Find("uiui", L"事实").first == 1);
    saveScheme(InputScheme::Flypy);
    checks.Check("Flypy immediately shares natural double pinyin learning", c.Find("uiui", L"事实").first == 1);
    saveScheme(InputScheme::FullPinyin);
    checks.Check("full pinyin immediately shares double pinyin learning", c.Find("shishi", L"事实").first == 1);
    c.Action(Action::Inspect, 0);
    checks.Check("full pinyin can forget a word learned in double pinyin", c.Action(Action::ForgetWord, 0) && c.response->commit.empty());
    saveScheme(InputScheme::Flypy);
    checks.Check("forgetting also restores the Flypy base rank", c.Find("uiui", L"事实").first == baseRank);

    prefs = LoadPreferences(settings); prefs.userLearning = false; SavePreferences(settings, prefs);
    for (const auto scheme : {InputScheme::NaturalDoublePinyin, InputScheme::Flypy}) {
      saveScheme(scheme);
      found = c.Find("uiui", L"事实"); c.Choose(found.second);
      checks.Check(std::string(InputSchemaId(scheme)) + " honors the paused Chinese learning preference",
          c.response->commit == L"事实" && c.Find("uiui", L"事实").first == baseRank);
    }
    prefs = LoadPreferences(settings); prefs.userLearning = true; SavePreferences(settings, prefs);
    found = c.Find("uiui", L"事实"); c.Choose(found.second);
    checks.Check("Flypy resumes native Chinese learning", c.Find("uiui", L"事实").first == 1);
    c.Action(Action::Inspect, 0);
    const ActionRequest forgetTicket{Action::ForgetWord, c.response->action.stamp, 0, false};
    const bool forgotten = c.client.StudyAction(forgetTicket); c.Read();
    checks.Check("Flypy forget preserves its composition without submitting text", forgotten && c.response->commit.empty() && c.response->status.composing);
    const bool forgotAgain = c.client.StudyAction(forgetTicket); c.Read();
    checks.Check("a repeated Flypy forget action is rejected", !forgotAgain && c.response->commit.empty());
    found = c.Find("uiui", L"事实"); c.Choose(found.second);
    checks.Check("final Flypy learning is ready for restart verification", c.Find("uiui", L"事实").first == 1 && LoadPreferences(settings).inputScheme == InputScheme::Flypy);
    c.client.ClearComposition();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    return 1;
  }
}

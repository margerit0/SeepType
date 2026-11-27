// SPDX-License-Identifier: GPL-3.0-or-later
// These tests exercise delivery/action invariants, not Chinese decoding.
use std::{cell::RefCell, rc::Rc};
use study_core::*;

#[derive(Default)]
struct Model { context: Context, config: Config, commits: Vec<String>, calls: usize, english: String, partial: bool, schema: String }
struct Fake(Rc<RefCell<Model>>);
impl Engine for Fake {
    fn read(&mut self) -> Result<Context> { Ok(self.0.borrow().context.clone()) }
    fn key(&mut self, code: u32, _: u32) -> Result<bool> {
        if code == SPACE { return self.select(0); }
        let mut m = self.0.borrow_mut();
        m.calls += 1;
        if code == BACKSPACE { m.context.input.pop(); }
        else { m.context.input.push(char::from_u32(code).unwrap()); }
        m.context.preedit = m.context.input.clone();
        m.context.caret = m.context.input.len();
        m.context.candidates = vec![Candidate { chinese: "你好".into(), english: "hello…".into() }];
        Ok(true)
    }
    fn clear(&mut self) -> Result<()> { self.0.borrow_mut().context = Context::default(); Ok(()) }
    fn select(&mut self, _: usize) -> Result<bool> {
        self.0.borrow_mut().commits.push("你好".into()); self.clear()?; Ok(true)
    }
    fn page(&mut self, _: bool) -> Result<bool> { self.0.borrow_mut().context.page += 1; Ok(true) }
    fn caret(&mut self, position: usize) -> Result<()> { self.0.borrow_mut().context.caret = position; Ok(()) }
    fn schema(&mut self, name: &str) -> Result<()> { self.0.borrow_mut().schema = name.into(); Ok(()) }
    fn configure(&mut self, config: &Config) -> Result<()> { self.0.borrow_mut().config = config.clone(); Ok(()) }
    fn inspect(&mut self, index: usize) -> Result<Inspection> {
        let mut m = self.0.borrow_mut();
        m.context.highlighted = index;
        let reason = if !m.config.english() { "disabled" } else if m.partial || m.context.caret != m.context.input.len() { "partial-composition" } else { "ready" };
        Ok(Inspection { chinese: "你好".into(), english: m.english.clone(), reason: reason.into(), reading: "ni hao".into() })
    }
    fn commit_english(&mut self) -> Result<bool> {
        let english = self.0.borrow().english.clone();
        self.0.borrow_mut().commits.push(english); self.clear()?; Ok(true)
    }
    fn forget(&mut self, _: usize) -> Result<bool> { Ok(true) }
    fn take_commit(&mut self) -> Result<Option<String>> { Ok(self.0.borrow_mut().commits.pop()) }
}

fn event(action: Action) -> Event { Event { generation: 1, action } }
fn fixture() -> (Session<Fake>, Rc<RefCell<Model>>) {
    let state = Rc::new(RefCell::new(Model { english: "hello; a complete definition".into(), ..Default::default() }));
    let mut session = Session::new(Fake(state.clone()));
    session.process(event(Action::Start { config: Config::default() })).unwrap();
    (session, state)
}
fn type_word(session: &mut Session<Fake>) -> Snapshot {
    let mut last = session.process(event(Action::Read)).unwrap();
    for code in "nihao".chars() { last = session.process(event(Action::Key { code: code as u32, modifiers: 0 })).unwrap(); }
    last
}
fn target(session: &mut Session<Fake>) -> Target {
    let snapshot = type_word(session);
    session.process(event(Action::Inspect { index: 0, revision: snapshot.revision })).unwrap().target.unwrap()
}

#[test]
fn stale_editor_event_never_reaches_engine() {
    let (mut session, state) = fixture();
    session.process(Event { generation: 2, action: Action::Start { config: Config::default() } }).unwrap();
    let result = session.process(event(Action::Key { code: 97, modifiers: 0 })).unwrap();
    assert!(result.commands.is_empty());
    assert_eq!(state.borrow().calls, 0);
    assert_eq!(result.notice, "stale-editor");
}
#[test]
fn duplicate_english_action_commits_once_and_uses_complete_dictionary_value() {
    let (mut session, _) = fixture();
    let target = target(&mut session);
    let command = Action::English { token: target.token };
    let first = session.process(event(command.clone())).unwrap();
    let duplicate = session.process(event(command)).unwrap();
    assert_eq!(first.commands[0].text, "hello; a complete definition");
    assert!(duplicate.commands.is_empty());
}
#[test]
fn dictionary_revalidation_rejects_changed_definition_without_losing_input() {
    let (mut session, state) = fixture();
    let target = target(&mut session);
    state.borrow_mut().english = "changed while panel was open".into();
    let result = session.process(event(Action::English { token: target.token })).unwrap();
    assert!(result.commands.is_empty());
    assert_eq!(result.context.input, "nihao");
    assert_eq!(result.notice, "target-changed");
}
#[test]
fn chinese_candidate_click_ignores_english_annotation() {
    let (mut session, _) = fixture();
    let before = type_word(&mut session);
    let clicked = session.process(event(Action::Select { index: 0, revision: before.revision })).unwrap();
    assert_eq!(clicked.commands.len(), 1);
    assert_eq!(clicked.commands[0].text, "你好");
}
#[test]
fn space_and_return_commit_raw_spelling_instead_of_selecting_candidates() {
    for code in [SPACE, RETURN] {
        for has_candidates in [true, false] {
            let (mut session, state) = fixture();
            let before = type_word(&mut session);
            {
                let mut m = state.borrow_mut();
                m.context.preedit = "ni hao".into();
                m.context.caret = 2;
                if !has_candidates { m.context.candidates.clear(); }
            }
            let pressed = session.process(event(Action::Key { code, modifiers: 0 })).unwrap();
            assert_eq!(pressed.commands, vec![EditorCommand { id: 1, kind: "commit".into(), text: "nihao".into() }]);
            assert!(pressed.context.input.is_empty() && pressed.context.candidates.is_empty());
            assert_eq!(state.borrow().calls, 5);
            let stale = session.process(event(Action::Select { index: 0, revision: before.revision })).unwrap();
            assert!(stale.commands.is_empty());
        }
    }
}
#[test]
fn space_and_return_keep_their_normal_behavior_without_composition() {
    let (mut session, _) = fixture();
    for ascii in [false, true] {
        session.process(event(Action::Mode { ascii })).unwrap();
        for (code, kind, text) in [(SPACE, "commit", " "), (RETURN, "action", "")] {
            let pressed = session.process(event(Action::Key { code, modifiers: 0 })).unwrap();
            assert_eq!(pressed.commands.len(), 1);
            assert_eq!(pressed.commands[0].kind, kind);
            assert_eq!(pressed.commands[0].text, text);
        }
    }
}
#[test]
fn english_toggle_invalidates_panel_and_preserves_learning_and_composition() {
    let (mut session, state) = fixture();
    let target = target(&mut session);
    let config = Config { show_english: false, ..Default::default() };
    let result = session.process(event(Action::Configure { config })).unwrap();
    assert!(!result.show_english);
    assert!(result.user_learning);
    assert_eq!(result.context.input, "nihao");
    assert!(result.context.candidates[0].english.is_empty());
    let stale = session.process(event(Action::English { token: target.token })).unwrap();
    assert!(stale.commands.is_empty());
    assert!(state.borrow().config.learning());
}
#[test]
fn partial_composition_cannot_submit_english() {
    let (mut session, state) = fixture();
    state.borrow_mut().partial = true;
    let target = target(&mut session);
    let result = session.process(event(Action::English { token: target.token })).unwrap();
    assert_eq!(result.context.input, "nihao");
    assert!(result.commands.is_empty());
}
#[test]
fn caret_motion_invalidates_inspected_action() {
    let (mut session, _) = fixture();
    let target = target(&mut session);
    session.process(event(Action::Caret { position: 2 })).unwrap();
    let result = session.process(event(Action::English { token: target.token })).unwrap();
    assert_eq!(result.context.caret, 2);
    assert!(result.commands.is_empty());
}
#[test]
fn stale_candidate_click_does_not_select_new_candidate() {
    let (mut session, _) = fixture();
    let old = type_word(&mut session);
    session.process(event(Action::Key { code: 109, modifiers: 0 })).unwrap();
    let result = session.process(event(Action::Select { index: 0, revision: old.revision })).unwrap();
    assert_eq!(result.context.input, "nihaom");
    assert!(result.commands.is_empty());
}
#[test]
fn schema_change_waits_for_composition_to_finish() {
    let (mut session, state) = fixture();
    type_word(&mut session);
    let config = Config { schema: "study_flypy".into(), ..Default::default() };
    let pending = session.process(event(Action::Configure { config })).unwrap();
    assert_eq!(pending.pending_schema.as_deref(), Some("study_flypy"));
    assert_eq!(state.borrow().schema, "study");
    let committed = session.process(event(Action::Key { code: SPACE, modifiers: 0 })).unwrap();
    assert_eq!(committed.commands[0].text, "nihao");
    assert_eq!(committed.schema, "study_flypy");
}
#[test]
fn password_bypasses_rime_and_disables_both_learning_features() {
    let (mut session, state) = fixture();
    let config = Config { sensitive: true, ..Default::default() };
    session.process(Event { generation: 2, action: Action::Start { config } }).unwrap();
    let result = session.process(Event { generation: 2, action: Action::Key { code: 97, modifiers: 0 } }).unwrap();
    assert!(!result.show_english && !result.user_learning && result.ascii_mode);
    assert_eq!(result.commands[0].text, "a");
    assert_eq!(state.borrow().calls, 0);
}
#[test]
fn no_personalized_learning_preserves_definitions() {
    let config = Config { no_personalization: true, ..Default::default() };
    assert!(!config.learning());
    assert!(config.english());
}
#[test]
fn old_pending_commit_is_discarded_on_editor_change() {
    let (mut session, state) = fixture();
    state.borrow_mut().commits.push("old editor text".into());
    let result = session.process(Event { generation: 2, action: Action::Start { config: Config::default() } }).unwrap();
    assert!(result.commands.is_empty());
    assert!(state.borrow().commits.is_empty());
}
#[test]
fn forgotten_word_does_not_edit_application_text() {
    let (mut session, _) = fixture();
    let target = target(&mut session);
    let result = session.process(event(Action::Forget { token: target.token })).unwrap();
    assert_eq!(result.context.input, "nihao");
    assert!(result.commands.is_empty());
    assert_eq!(result.notice, "forgotten");
}

#[test]
fn queued_preferences_preserve_newer_mode_and_bound_editor_privacy() {
    let (mut session, state) = fixture();
    session.process(event(Action::Mode { ascii: true })).unwrap();
    let stale_preferences = Config { show_english: false, ..Default::default() };
    let result = session.process(event(Action::Configure { config: stale_preferences })).unwrap();
    assert!(result.ascii_mode);
    assert!(!result.show_english);
    let config = Config { sensitive: true, no_personalization: true, ..Default::default() };
    session.process(Event { generation: 2, action: Action::Start { config } }).unwrap();
    let result = session.process(Event { generation: 2, action: Action::Configure { config: Config::default() } }).unwrap();
    assert!(result.ascii_mode && !result.show_english && !result.user_learning);
    assert!(state.borrow().config.sensitive && state.borrow().config.no_personalization);
}

#[test]
fn verified_editor_restart_preserves_composition_but_expires_candidate_actions() {
    let (mut session, _) = fixture();
    let target = target(&mut session);
    let result = session.process(Event { generation: 2, action: Action::Restart {
        config: Config::default(), previous_generation: 1, revision: target.revision,
    } }).unwrap();
    assert_eq!(result.context.input, "nihao");
    assert!(result.commands.is_empty() && result.target.is_none());
    let stale = session.process(Event { generation: 2, action: Action::English { token: target.token } }).unwrap();
    assert!(stale.commands.is_empty());
}

#[test]
fn restart_with_an_unseen_engine_revision_cannot_restore_old_composition() {
    let (mut session, _) = fixture();
    let visible = type_word(&mut session);
    session.process(event(Action::Key { code: 109, modifiers: 0 })).unwrap();
    let result = session.process(Event { generation: 2, action: Action::Restart {
        config: Config::default(), previous_generation: 1, revision: visible.revision,
    } }).unwrap();
    assert!(result.context.input.is_empty() && result.commands.is_empty());
    assert_eq!(result.notice, "restart-discarded");
}

fn spelling_session(ascii_mode: bool) -> Session<Fake> {
    let lexicon = EnglishLexicon::from_index("home\t1\nhomeless\t4\nhometown\t5\nhomework\t2\n").unwrap();
    let mut session = Session::with_english_lexicon(Fake(Rc::default()), lexicon);
    let config = Config { ascii_mode, suggest_spellings: true, ..Default::default() };
    session.process(event(Action::Start { config })).unwrap();
    session
}

fn type_spelling(session: &mut Session<Fake>, text: &str) -> Snapshot {
    let mut last = session.process(event(Action::Read)).unwrap();
    for code in text.bytes() {
        last = session.process(event(Action::Key { code: code.into(), modifiers: 0 })).unwrap();
    }
    last
}

#[test]
fn english_completion_ranks_words_preserves_case_and_consumes_selection() {
    let mut session = spelling_session(true);
    let before = type_spelling(&mut session, "Hom");
    assert_eq!(before.context.preedit, "Hom");
    assert!(before.commands.is_empty());
    assert_eq!(before.spelling_candidates, ["Hom", "Home", "Homework", "Homeless"]);
    let tap = Action::SelectSpelling { index: 2, revision: before.revision };
    let selected = session.process(event(tap.clone())).unwrap();
    assert_eq!(selected.commands[0].text, "Homework");
    assert!(selected.context.input.is_empty() && selected.spelling_candidates.is_empty());
    assert!(session.process(event(tap)).unwrap().commands.is_empty());
    assert_eq!(type_spelling(&mut session, "HOME").spelling_candidates, ["HOME", "HOMEWORK", "HOMELESS", "HOMETOWN"]);
}

#[test]
fn english_boundaries_commit_raw_input_and_keep_space_and_editor_actions() {
    let mut session = spelling_session(true);
    assert_eq!(type_spelling(&mut session, "Qzx").spelling_candidates, ["Qzx"]);
    let backspace = session.process(event(Action::Key { code: BACKSPACE, modifiers: 0 })).unwrap();
    assert_eq!(backspace.context.input, "Qz");
    assert!(backspace.commands.is_empty());
    let space = session.process(event(Action::Key { code: SPACE, modifiers: 0 })).unwrap();
    assert_eq!(space.commands.iter().map(|c| c.text.as_str()).collect::<Vec<_>>(), ["Qz", " "]);
    type_spelling(&mut session, "hom");
    let enter = session.process(event(Action::Key { code: RETURN, modifiers: 0 })).unwrap();
    assert_eq!(enter.commands[0].text, "hom");
    assert_eq!(enter.commands[1].kind, "action");
    type_spelling(&mut session, "Home");
    let switch = session.process(event(Action::Mode { ascii: false })).unwrap();
    assert_eq!(switch.commands[0].text, "Home");
    assert!(!switch.ascii_mode && switch.spelling_candidates.is_empty());
}

#[test]
fn mixed_spelling_uses_the_raw_code_without_reindexing_chinese_candidates() {
    let mut session = spelling_session(false);
    let before = type_spelling(&mut session, "home");
    assert_eq!(before.spelling_candidates, ["home"]);
    assert_eq!(before.context.candidates[0].chinese, "你好");
    let picked = session.process(event(Action::SelectSpelling { index: 0, revision: before.revision })).unwrap();
    assert_eq!(picked.commands[0].text, "home");
    let pinyin = type_spelling(&mut session, "nihao");
    assert!(pinyin.spelling_candidates.is_empty());
    let picked = session.process(event(Action::Select { index: 0, revision: pinyin.revision })).unwrap();
    assert_eq!(picked.commands[0].text, "你好");
}

#[test]
fn new_or_protected_editors_cannot_reuse_pending_english_spelling() {
    let mut session = spelling_session(true);
    let before = type_spelling(&mut session, "home");
    let secure = Config { sensitive: true, suggest_spellings: true, ..Default::default() };
    let start = session.process(Event { generation: 2, action: Action::Start { config: secure } }).unwrap();
    assert!(start.context.input.is_empty() && start.commands.is_empty());
    let stale = session.process(event(Action::SelectSpelling { index: 0, revision: before.revision })).unwrap();
    assert!(stale.commands.is_empty());
    let direct = session.process(Event { generation: 2, action: Action::Key { code: 104, modifiers: 0 } }).unwrap();
    assert_eq!(direct.commands[0].text, "h");
    assert!(direct.context.input.is_empty() && direct.spelling_candidates.is_empty());
}

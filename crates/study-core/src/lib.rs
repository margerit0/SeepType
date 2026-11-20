// SPDX-License-Identifier: GPL-3.0-or-later
//! Platform-independent session policy. The engine, never UI text, is the
//! authority for candidate selection, English eligibility and learned entries.
use serde::{Deserialize, Serialize};

pub type Result<T> = std::result::Result<T, String>;
pub const BACKSPACE: u32 = 0xff08;
pub const RETURN: u32 = 0xff0d;
pub const SPACE: u32 = b' ' as u32;

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Candidate {
    pub chinese: String,
    pub english: String,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Context {
    pub input: String,
    pub preedit: String,
    pub caret: usize,
    pub preedit_cursor: usize,
    pub page: usize,
    pub page_size: usize,
    pub highlighted: usize,
    pub last_page: bool,
    pub candidates: Vec<Candidate>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default, rename_all = "camelCase")]
pub struct Config {
    pub version: u32,
    pub schema: String,
    pub show_english: bool,
    pub user_learning: bool,
    pub ascii_mode: bool,
    pub sensitive: bool,
    pub no_personalization: bool,
}
impl Default for Config {
    fn default() -> Self {
        Self { version: 1, schema: "study".into(), show_english: true, user_learning: true,
            ascii_mode: false, sensitive: false, no_personalization: false }
    }
}
impl Config {
    pub fn english(&self) -> bool { self.show_english && !self.sensitive }
    pub fn learning(&self) -> bool { self.user_learning && !self.sensitive && !self.no_personalization }
    pub fn ascii(&self) -> bool { self.ascii_mode || self.sensitive }
    fn validate(&self) -> Result<()> {
        if self.version != 1 || !["study", "study_double_pinyin", "study_flypy"].contains(&self.schema.as_str()) {
            return Err("unsupported-config".into());
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct Inspection {
    pub chinese: String,
    pub english: String,
    pub reason: String,
}

pub trait Engine {
    fn read(&mut self) -> Result<Context>;
    fn key(&mut self, code: u32, modifiers: u32) -> Result<bool>;
    fn clear(&mut self) -> Result<()>;
    fn select(&mut self, index: usize) -> Result<bool>;
    fn page(&mut self, backwards: bool) -> Result<bool>;
    fn caret(&mut self, position: usize) -> Result<()>;
    fn schema(&mut self, schema: &str) -> Result<()>;
    /// Must preserve the composition, caret and selected candidate.
    fn configure(&mut self, config: &Config) -> Result<()>;
    fn inspect(&mut self, index: usize) -> Result<Inspection>;
    fn commit_english(&mut self) -> Result<bool>;
    fn forget(&mut self, index: usize) -> Result<bool>;
    fn take_commit(&mut self) -> Result<Option<String>>;
}

#[derive(Clone, Debug, Deserialize)]
pub struct Event {
    pub generation: u64,
    #[serde(flatten)]
    pub action: Action,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum Action {
    Start { config: Config },
    Restart { config: Config, #[serde(rename = "previousGeneration")] previous_generation: u64, revision: u64 },
    Key { code: u32, #[serde(default)] modifiers: u32 },
    Literal { text: String },
    Select { index: usize, revision: u64 },
    Inspect { index: usize, revision: u64 },
    English { token: String },
    Forget { token: String },
    Page { backwards: bool, revision: u64 },
    Caret { position: usize },
    Configure { config: Config },
    Mode { ascii: bool },
    Clear,
    Dismiss,
    Read,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Target {
    pub token: String,
    pub generation: u64,
    pub revision: u64,
    pub index: usize,
    pub page: usize,
    pub input: String,
    pub caret: usize,
    pub chinese: String,
    pub english: String,
    pub reason: String,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EditorCommand {
    pub id: u64,
    pub kind: String,
    pub text: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    pub ok: bool,
    pub generation: u64,
    pub revision: u64,
    pub context: Context,
    pub schema: String,
    pub pending_schema: Option<String>,
    pub show_english: bool,
    pub user_learning: bool,
    pub ascii_mode: bool,
    pub target: Option<Target>,
    pub commands: Vec<EditorCommand>,
    pub notice: String,
}

pub struct Session<E: Engine> {
    engine: E,
    generation: u64,
    revision: u64,
    next_commit: u64,
    config: Config,
    active_schema: String,
    target: Option<Target>,
}

impl<E: Engine> Session<E> {
    pub fn new(engine: E) -> Self {
        Self { engine, generation: 0, revision: 0, next_commit: 0, config: Config::default(),
               active_schema: String::new(), target: None }
    }

    fn invalidate(&mut self) -> Result<()> {
        self.revision = self.revision.checked_add(1).ok_or("revision-exhausted")?;
        self.target = None;
        Ok(())
    }

    fn command(&mut self, commands: &mut Vec<EditorCommand>, kind: &str, text: String) -> Result<()> {
        self.next_commit = self.next_commit.checked_add(1).ok_or("commit-id-exhausted")?;
        commands.push(EditorCommand { id: self.next_commit, kind: kind.into(), text });
        Ok(())
    }

    fn drain(&mut self, commands: &mut Vec<EditorCommand>) -> Result<()> {
        if let Some(text) = self.engine.take_commit()? {
            if !text.is_empty() { self.command(commands, "commit", text)?; }
        }
        Ok(())
    }

    fn finish_word(&mut self, commands: &mut Vec<EditorCommand>) -> Result<()> {
        // A punctuation/mode key finishes remaining Chinese segments in order.
        for _ in 0..64 {
            let before = self.engine.read()?;
            if before.input.is_empty() { return Ok(()); }
            if before.candidates.is_empty() {
                self.engine.clear()?;
                self.command(commands, "commit", before.input)?;
                return Ok(());
            }
            self.engine.select(before.highlighted)?;
            self.drain(commands)?;
            if self.engine.read()? == before { return Err("composition-did-not-progress".into()); }
        }
        Err("composition-too-long".into())
    }

    fn snapshot(&mut self, commands: Vec<EditorCommand>, notice: String) -> Result<Snapshot> {
        let mut context = self.engine.read()?;
        if context.input.is_empty() && self.active_schema != self.config.schema && self.generation != 0 {
            self.engine.schema(&self.config.schema)?;
            self.engine.configure(&self.config)?;
            self.active_schema = self.config.schema.clone();
            context = self.engine.read()?;
        }
        if !self.config.english() {
            for candidate in &mut context.candidates { candidate.english.clear(); }
        }
        Ok(Snapshot { ok: true, generation: self.generation, revision: self.revision, context,
            schema: self.active_schema.clone(),
            pending_schema: (self.active_schema != self.config.schema).then(|| self.config.schema.clone()),
            show_english: self.config.english(), user_learning: self.config.learning(), ascii_mode: self.config.ascii(),
            target: self.target.clone(), commands, notice })
    }

    fn matching_target(&mut self, token: &str) -> Result<Option<Target>> {
        let Some(target) = self.target.clone() else { return Ok(None) };
        if target.token != token || target.generation != self.generation || target.revision != self.revision {
            return Ok(None);
        }
        let current = self.engine.read()?;
        let matches = current.input == target.input && current.caret == target.caret && current.page == target.page
            && current.highlighted == target.index
            && current.candidates.get(target.index).is_some_and(|c| c.chinese == target.chinese);
        Ok(matches.then_some(target))
    }

    pub fn process(&mut self, event: Event) -> Result<Snapshot> {
        let mut commands = vec![];
        let mut notice = String::new();
        let starting = match &event.action {
            Action::Start { config } => Some((config, false)),
            Action::Restart { config, previous_generation, revision } =>
                Some((config, *previous_generation == self.generation && *revision == self.revision && self.generation != 0)),
            _ => None,
        };
        if let Some((config, resume)) = starting {
            config.validate()?;
            if event.generation <= self.generation { return self.snapshot(commands, "stale-editor".into()); }
            if !resume { self.engine.clear()?; }
            // Old, unconsumed engine output can never be delivered to a new editor.
            let _ = self.engine.take_commit()?;
            let previous_ascii = self.config.ascii_mode;
            self.generation = event.generation;
            self.config = config.clone();
            if resume { self.config.ascii_mode = previous_ascii; }
            self.invalidate()?;
            if !resume {
                self.engine.schema(&self.config.schema)?;
                self.active_schema = self.config.schema.clone();
                if matches!(event.action, Action::Restart { .. }) { notice = "restart-discarded".into(); }
            }
            self.engine.configure(&self.config)?;
            return self.snapshot(commands, notice);
        }
        if event.generation != self.generation || self.generation == 0 {
            return self.snapshot(commands, "stale-editor".into());
        }

        match event.action {
            Action::Start { .. } | Action::Restart { .. } => unreachable!(),
            Action::Read => {},
            Action::Dismiss => { self.invalidate()?; },
            Action::Clear => { self.invalidate()?; self.engine.clear()?; },
            Action::Key { code, modifiers } => {
                self.invalidate()?;
                let before = self.engine.read()?;
                if self.config.ascii() {
                    match code {
                        BACKSPACE => self.command(&mut commands, "delete", String::new())?,
                        RETURN => self.command(&mut commands, "action", String::new())?,
                        _ => {
                            if let Some(c) = char::from_u32(code).filter(|c| !c.is_control() && code < 0xff00) {
                                self.command(&mut commands, "commit", c.to_string())?;
                            }
                        }
                    }
                } else if code == BACKSPACE && before.input.is_empty() {
                    self.command(&mut commands, "delete", String::new())?;
                } else if code == RETURN || (code == SPACE && modifiers == 0) {
                    if !before.input.is_empty() {
                        // Commit the typed spelling, not formatted preedit or a candidate.
                        self.engine.clear()?;
                        self.command(&mut commands, "commit", before.input)?;
                    } else if code == RETURN {
                        self.command(&mut commands, "action", String::new())?;
                    } else {
                        self.command(&mut commands, "commit", " ".into())?;
                    }
                } else if !self.engine.key(code, modifiers)? {
                    self.drain(&mut commands)?;
                    if let Some(c) = char::from_u32(code).filter(|c| !c.is_control() && code < 0xff00) {
                        self.command(&mut commands, "commit", c.to_string())?;
                    }
                }
            },
            Action::Literal { text } => {
                if text.is_empty() || text.len() > 4096 || text.contains('\0') { return Err("invalid-literal".into()); }
                self.invalidate()?;
                self.finish_word(&mut commands)?;
                self.command(&mut commands, "commit", text)?;
            },
            Action::Select { index, revision } => {
                if revision != self.revision || index >= self.engine.read()?.candidates.len() {
                    return self.snapshot(commands, "stale-candidate".into());
                }
                self.invalidate()?;
                if !self.engine.select(index)? { notice = "selection-unavailable".into(); }
            },
            Action::Page { backwards, revision } => {
                if revision != self.revision { return self.snapshot(commands, "stale-candidate".into()); }
                self.invalidate()?;
                self.engine.page(backwards)?;
            },
            Action::Caret { position } => {
                if position > self.engine.read()?.input.len() { return Err("invalid-caret".into()); }
                self.invalidate()?;
                self.engine.caret(position)?;
            },
            Action::Configure { mut config } => {
                config.validate()?;
                self.invalidate()?;
                // Layout/theme changes are local. Engine preferences take
                // effect immediately; a schema waits for an empty composition.
                // A queued preference snapshot cannot override a newer Mode
                // event or weaken the privacy policy bound by Start.
                config.ascii_mode = self.config.ascii_mode;
                config.sensitive = self.config.sensitive;
                config.no_personalization = self.config.no_personalization;
                self.engine.configure(&config)?;
                self.config = config;
            },
            Action::Mode { ascii } => {
                self.invalidate()?;
                self.finish_word(&mut commands)?;
                self.config.ascii_mode = ascii;
                self.engine.configure(&self.config)?;
            },
            Action::Inspect { index, revision } => {
                if revision != self.revision || index >= self.engine.read()?.candidates.len() {
                    return self.snapshot(commands, "stale-candidate".into());
                }
                self.invalidate()?;
                let inspection = self.engine.inspect(index)?;
                let context = self.engine.read()?;
                if context.highlighted != index || context.candidates.get(index).is_none_or(|c| c.chinese != inspection.chinese) {
                    return self.snapshot(commands, "target-unavailable".into());
                }
                self.target = Some(Target { token: format!("{}:{}", self.generation, self.revision),
                    generation: self.generation, revision: self.revision, index, page: context.page,
                    input: context.input, caret: context.caret, chinese: inspection.chinese,
                    english: inspection.english, reason: inspection.reason });
            },
            Action::English { token } => {
                let Some(target) = self.matching_target(&token)? else { return self.snapshot(commands, "stale-target".into()) };
                if !self.config.english() || target.reason != "ready" {
                    return self.snapshot(commands, "english-unavailable".into());
                }
                let verified = self.engine.inspect(target.index)?;
                if verified.reason != "ready" || verified.chinese != target.chinese || verified.english != target.english {
                    self.invalidate()?;
                    return self.snapshot(commands, "target-changed".into());
                }
                self.invalidate()?; // Consume the action before crossing the FFI boundary.
                if !self.engine.commit_english()? { notice = "english-unavailable".into(); }
            },
            Action::Forget { token } => {
                let Some(target) = self.matching_target(&token)? else { return self.snapshot(commands, "stale-target".into()) };
                if self.config.sensitive { return self.snapshot(commands, "private-editor".into()); }
                self.invalidate()?;
                let success = self.engine.forget(target.index)?;
                let after = self.engine.read()?;
                if after.input != target.input || after.caret != target.caret { return Err("forget-changed-composition".into()); }
                notice = if success { "forgotten" } else { "nothing-to-forget" }.into();
            }
        }
        self.drain(&mut commands)?;
        self.snapshot(commands, notice)
    }
}

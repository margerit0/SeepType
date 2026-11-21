// SPDX-License-Identifier: GPL-3.0-or-later
//! The sole owner of one Android Rime runtime and session. All borrowed C text
//! is copied before its lease is freed, including error and early-return paths.
use std::ffi::{c_char, CStr, CString};
use std::thread::{self, ThreadId};
use study_core::{Candidate, Config, Context, Engine, Inspection, Result};
use study_rime_sys as ffi;

fn cstring(value: &str) -> Result<CString> {
    CString::new(value).map_err(|_| "embedded-nul".into())
}

// SAFETY: Called only for nullable, NUL-terminated strings owned by our bridge
// and while their containing view/text lease remains alive.
unsafe fn copied(pointer: *const c_char) -> Result<String> {
    if pointer.is_null() { return Ok(String::new()); }
    CStr::from_ptr(pointer).to_str().map(str::to_owned).map_err(|_| "invalid-native-utf8".into())
}

fn checked(value: i32) -> Result<bool> {
    if value < 0 { Err("native-operation-failed".into()) } else { Ok(value != 0) }
}

struct ViewLease(*const ffi::View);
impl Drop for ViewLease {
    fn drop(&mut self) { unsafe { ffi::study_rime_free_view(self.0); } }
}
struct TextLease(*mut c_char);
impl Drop for TextLease {
    fn drop(&mut self) { unsafe { ffi::study_rime_free_text(self.0); } }
}

pub struct RimeEngine {
    session: usize,
    owner: ThreadId,
    // Retain trait strings until finalization even if an upstream version
    // elects to retain those pointers during initialization.
    _paths: [CString; 3],
    english: bool,
    ascii: bool,
}

impl RimeEngine {
    pub fn new(shared: &str, user: &str, build: &str) -> Result<Self> {
        let paths = [cstring(shared)?, cstring(user)?, cstring(build)?];
        if !checked(unsafe { ffi::study_rime_initialize(paths[0].as_ptr(), paths[1].as_ptr(), paths[2].as_ptr()) })? {
            return Err("rime-initialization-failed".into());
        }
        let session = unsafe { ffi::study_rime_session() };
        if session == 0 {
            unsafe { ffi::study_rime_finalize(); }
            return Err("rime-session-failed".into());
        }
        let mut engine = Self { session, owner: thread::current().id(), _paths: paths, english: true, ascii: false };
        engine.schema("study")?;
        if engine.property("study_protocol")? != "1" || engine.property("study_load_state")? != "ready" {
            return Err("rime-lua-data-not-ready".into());
        }
        Ok(engine)
    }

    fn affinity(&self) -> Result<()> {
        if self.owner != thread::current().id() { return Err("wrong-engine-thread".into()); }
        Ok(())
    }

    fn set_property(&self, key: &str, value: &str) -> Result<()> {
        self.affinity()?;
        checked(unsafe { ffi::study_rime_property(self.session, cstring(key)?.as_ptr(), cstring(value)?.as_ptr()) })?;
        Ok(())
    }

    fn property(&self, key: &str) -> Result<String> {
        self.affinity()?;
        let text = TextLease(unsafe { ffi::study_rime_get_property(self.session, cstring(key)?.as_ptr()) });
        unsafe { copied(text.0) }
    }

    fn option(&self, key: &str, value: bool) -> Result<()> {
        self.affinity()?;
        if !checked(unsafe { ffi::study_rime_option(self.session, cstring(key)?.as_ptr(), i32::from(value)) })? {
            return Err("rime-option-rejected".into());
        }
        Ok(())
    }

    fn request(&mut self, request: &str) -> Result<bool> {
        if self.property("study_protocol")? != "1" { return Ok(false); }
        for key in ["study_response", "study_target_text", "study_target_english", "study_target_reason", "study_target_reading"] {
            self.set_property(key, "")?;
        }
        self.set_property("study_request", request)?;
        let handled = self.key(0, 0)?;
        self.set_property("study_request", "")?;
        Ok(handled && self.property("study_response")? == request)
    }

    pub fn version(&self) -> Result<String> {
        self.affinity()?;
        unsafe { copied(ffi::study_rime_version()) }
    }
}

impl Engine for RimeEngine {
    fn read(&mut self) -> Result<Context> {
        self.affinity()?;
        let view = ViewLease(unsafe { ffi::study_rime_read(self.session) });
        if view.0.is_null() { return Err("rime-context-unavailable".into()); }
        // SAFETY: The bridge allocates a complete, immutable View with at most
        // 128 candidate records. ViewLease outlives all reads and always frees it.
        unsafe {
            let value = &*view.0;
            if value.candidate_count > 128 || (value.candidate_count != 0 && value.candidates.is_null()) {
                return Err("invalid-native-candidate-count".into());
            }
            let entries = if value.candidate_count == 0 { &[] } else {
                std::slice::from_raw_parts(value.candidates, value.candidate_count)
            };
            let candidates = entries.iter().map(|item| Ok(Candidate { chinese: copied(item.text)?, english: copied(item.english)? })).collect::<Result<Vec<_>>>()?;
            Ok(Context { input: copied(value.input)?, preedit: copied(value.preedit)?, caret: value.caret,
                preedit_cursor: value.preedit_cursor.max(0) as usize, page: value.page.max(0) as usize,
                page_size: value.page_size.max(0) as usize, highlighted: value.highlighted.max(0) as usize,
                last_page: value.last_page != 0, candidates })
        }
    }
    fn key(&mut self, code: u32, modifiers: u32) -> Result<bool> {
        self.affinity()?;
        if code > 0x10ffff || modifiers > 0xffff { return Err("invalid-key".into()); }
        checked(unsafe { ffi::study_rime_key(self.session, code as i32, modifiers as i32) })
    }
    fn clear(&mut self) -> Result<()> {
        self.affinity()?;
        checked(unsafe { ffi::study_rime_clear(self.session) })?;
        Ok(())
    }
    fn select(&mut self, index: usize) -> Result<bool> {
        self.affinity()?;
        checked(unsafe { ffi::study_rime_select(self.session, index) })
    }
    fn page(&mut self, backwards: bool) -> Result<bool> {
        self.affinity()?;
        checked(unsafe { ffi::study_rime_page(self.session, i32::from(backwards)) })
    }
    fn caret(&mut self, position: usize) -> Result<()> {
        self.affinity()?;
        checked(unsafe { ffi::study_rime_caret(self.session, position) })?;
        Ok(())
    }
    fn schema(&mut self, schema: &str) -> Result<()> {
        self.affinity()?;
        if !checked(unsafe { ffi::study_rime_schema(self.session, cstring(schema)?.as_ptr()) })? {
            return Err("rime-schema-unavailable".into());
        }
        self.english = true;
        self.ascii = false;
        Ok(())
    }
    fn configure(&mut self, config: &Config) -> Result<()> {
        self.affinity()?;
        let before = self.read()?;
        if !before.input.is_empty() && self.ascii != config.ascii() {
            return Err("mode-change-requires-empty-composition".into());
        }
        self.set_property("study_user_learning", if config.learning() { "1" } else { "0" })?;
        let has_selection = before.candidates.get(before.highlighted).is_some();
        let absolute = before.page * before.page_size + before.highlighted;
        if self.english != config.english() {
            self.option("learning_mode", config.english())?;
            if has_selection { checked(unsafe { ffi::study_rime_highlight(self.session, absolute, 1) })?; }
            let after = self.read()?;
            let preserved = before.input == after.input && before.caret == after.caret
                && (!has_selection || (before.page == after.page && before.highlighted == after.highlighted
                    && before.candidates[before.highlighted].chinese == after.candidates.get(after.highlighted).map(|c| c.chinese.as_str()).unwrap_or("")));
            if !preserved {
                self.option("learning_mode", self.english)?;
                if has_selection { checked(unsafe { ffi::study_rime_highlight(self.session, absolute, 1) })?; }
                return Err("config-did-not-preserve-composition".into());
            }
            self.english = config.english();
        }
        self.option("ascii_mode", config.ascii())?;
        self.ascii = config.ascii();
        Ok(())
    }
    fn inspect(&mut self, index: usize) -> Result<Inspection> {
        self.affinity()?;
        let before = self.read()?;
        if index >= before.candidates.len() {
            return Err("rime-candidate-unavailable".into());
        }
        // Rime returns false when Highlight is a no-op. The currently selected
        // candidate is still inspectable (and must be revalidated on commit).
        if before.highlighted != index {
            checked(unsafe { ffi::study_rime_highlight(self.session, index, 0) })?;
            let after = self.read()?;
            if after.page != before.page || after.highlighted != index
                || after.candidates.get(index).map(|c| &c.chinese) != Some(&before.candidates[index].chinese) {
                return Err("rime-highlight-unavailable".into());
            }
        }
        if !self.request("inspect-v1")? {
            return Err("rime-inspection-protocol-unavailable".into());
        }
        Ok(Inspection { chinese: self.property("study_target_text")?, english: self.property("study_target_english")?,
            reason: self.property("study_target_reason")?, reading: self.property("study_target_reading")? })
    }
    fn commit_english(&mut self) -> Result<bool> {
        Ok(self.request("commit-v1")? && self.property("study_action")? == "english-committed")
    }
    fn forget(&mut self, index: usize) -> Result<bool> {
        self.affinity()?;
        checked(unsafe { ffi::study_rime_forget(self.session, index) })
    }
    fn take_commit(&mut self) -> Result<Option<String>> {
        self.affinity()?;
        let text = TextLease(unsafe { ffi::study_rime_take_commit(self.session) });
        if text.0.is_null() { return Ok(None); }
        Ok(Some(unsafe { copied(text.0)? }))
    }
}
impl Drop for RimeEngine {
    fn drop(&mut self) {
        // JNI destruction is queued on the same serial worker as initialization.
        // If a caller violates affinity, leak rather than concurrently finalize.
        if self.owner == thread::current().id() {
            unsafe { ffi::study_rime_destroy_session(self.session); ffi::study_rime_finalize(); }
        }
    }
}

// SPDX-License-Identifier: GPL-3.0-or-later
//! Manually reviewed bindings to android/native/bridge.h, not Rime's function table.
use std::ffi::{c_char, c_int};

#[repr(C)]
pub struct Candidate { pub text: *const c_char, pub english: *const c_char }
#[repr(C)]
pub struct View {
    pub input: *const c_char,
    pub preedit: *const c_char,
    pub caret: usize,
    pub preedit_cursor: i32,
    pub page: i32,
    pub page_size: i32,
    pub highlighted: i32,
    pub last_page: i32,
    pub candidate_count: usize,
    pub candidates: *const Candidate,
}

unsafe extern "C" {
    pub fn study_rime_initialize(shared: *const c_char, user: *const c_char, build: *const c_char) -> c_int;
    pub fn study_rime_finalize();
    pub fn study_rime_session() -> usize;
    pub fn study_rime_destroy_session(session: usize);
    pub fn study_rime_key(session: usize, code: c_int, modifiers: c_int) -> c_int;
    pub fn study_rime_select(session: usize, index: usize) -> c_int;
    pub fn study_rime_highlight(session: usize, index: usize, absolute: c_int) -> c_int;
    pub fn study_rime_forget(session: usize, index: usize) -> c_int;
    pub fn study_rime_page(session: usize, backwards: c_int) -> c_int;
    pub fn study_rime_schema(session: usize, schema: *const c_char) -> c_int;
    pub fn study_rime_option(session: usize, key: *const c_char, value: c_int) -> c_int;
    pub fn study_rime_property(session: usize, key: *const c_char, value: *const c_char) -> c_int;
    pub fn study_rime_clear(session: usize) -> c_int;
    pub fn study_rime_caret(session: usize, caret: usize) -> c_int;
    pub fn study_rime_read(session: usize) -> *const View;
    pub fn study_rime_free_view(view: *const View);
    pub fn study_rime_take_commit(session: usize) -> *mut c_char;
    pub fn study_rime_get_property(session: usize, key: *const c_char) -> *mut c_char;
    pub fn study_rime_free_text(text: *mut c_char);
    pub fn study_rime_error() -> *const c_char;
    pub fn study_rime_version() -> *const c_char;
}

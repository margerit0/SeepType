// SPDX-License-Identifier: GPL-3.0-or-later
//! JNI owns opaque, monotonic IDs, never Java-supplied native pointers.
use jni::{objects::{JObject, JString}, sys::{jlong, jstring}, JNIEnv};
use std::{fs, io, panic::{catch_unwind, AssertUnwindSafe}, path::Path, sync::{Mutex, OnceLock}, thread::{self, ThreadId}};
use study_core::{EnglishLexicon, Event, Session};
use study_rime::RimeEngine;

struct Runtime { id: i64, owner: ThreadId, session: Session<RimeEngine>, version: String }
struct Registry { next: i64, runtime: Option<Runtime> }
static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
fn registry() -> &'static Mutex<Registry> { REGISTRY.get_or_init(|| Mutex::new(Registry { next: 0, runtime: None })) }

fn boundary<T>(env: &mut JNIEnv, work: impl FnOnce(&mut JNIEnv) -> Result<T, String>) -> Option<T> {
    match catch_unwind(AssertUnwindSafe(|| work(env))) {
        Ok(Ok(value)) => Some(value),
        Ok(Err(message)) => { let _ = env.throw_new("java/lang/IllegalStateException", message); None },
        Err(_) => { let _ = env.throw_new("java/lang/IllegalStateException", "native-panic-contained"); None }
    }
}

fn string(env: &mut JNIEnv, value: &JString) -> Result<String, String> {
    env.get_string(value).map(Into::into).map_err(|_| "invalid-jni-string".into())
}

#[no_mangle]
pub extern "system" fn Java_org_studyime_android_engine_NativeCore_create(mut env: JNIEnv, _: JObject, shared: JString, user: JString, build: JString) -> jlong {
    boundary(&mut env, |env| {
        let (shared, user, build) = (string(env, &shared)?, string(env, &user)?, string(env, &build)?);
        let mut registry = registry().lock().map_err(|_| "engine-poisoned")?;
        if registry.runtime.is_some() { return Err("engine-already-owned".into()); }
        let engine = RimeEngine::new(&shared, &user, &build)?;
        let lexicon = match fs::read_to_string(Path::new(&shared).join("english-completions.tsv")) {
            Ok(data) => EnglishLexicon::from_index(&data)?,
            Err(error) if error.kind() == io::ErrorKind::NotFound => EnglishLexicon::default(),
            Err(_) => return Err("english-index-unreadable".into()),
        };
        let version = engine.version()?;
        registry.next = registry.next.checked_add(1).ok_or("handle-exhausted")?;
        let id = registry.next;
        registry.runtime = Some(Runtime { id, owner: thread::current().id(), session: Session::with_english_lexicon(engine, lexicon), version });
        Ok(id)
    }).unwrap_or(0)
}

#[no_mangle]
pub extern "system" fn Java_org_studyime_android_engine_NativeCore_dispatch(mut env: JNIEnv, _: JObject, id: jlong, input: JString) -> jstring {
    boundary(&mut env, |env| {
        let text = string(env, &input)?;
        if text.len() > 32_768 { return Err("oversize-event".into()); }
        let event: Event = serde_json::from_str(&text).map_err(|_| "invalid-event")?;
        let mut registry = registry().lock().map_err(|_| "engine-poisoned")?;
        let runtime = registry.runtime.as_mut().filter(|r| r.id == id).ok_or("invalid-engine-handle")?;
        if runtime.owner != thread::current().id() { return Err("wrong-engine-thread".into()); }
        let generation = event.generation;
        let response = match runtime.session.process(event) {
            Ok(snapshot) => serde_json::to_string(&snapshot).map_err(|_| "snapshot-encoding-failed")?,
            Err(error) => serde_json::json!({"ok": false, "generation": generation, "error": error, "commands": []}).to_string()
        };
        env.new_string(response).map(JString::into_raw).map_err(|_| "jni-allocation-failed".into())
    }).unwrap_or(std::ptr::null_mut())
}

#[no_mangle]
pub extern "system" fn Java_org_studyime_android_engine_NativeCore_destroy(mut env: JNIEnv, _: JObject, id: jlong) {
    boundary(&mut env, |_| {
        let mut registry = registry().lock().map_err(|_| "engine-poisoned")?;
        let runtime = registry.runtime.as_ref().filter(|r| r.id == id).ok_or("invalid-engine-handle")?;
        if runtime.owner != thread::current().id() { return Err("wrong-engine-thread".into()); }
        registry.runtime.take();
        Ok(())
    });
}

#[no_mangle]
pub extern "system" fn Java_org_studyime_android_engine_NativeCore_version(mut env: JNIEnv, _: JObject, id: jlong) -> jstring {
    boundary(&mut env, |env| {
        let registry = registry().lock().map_err(|_| "engine-poisoned")?;
        let runtime = registry.runtime.as_ref().filter(|r| r.id == id).ok_or("invalid-engine-handle")?;
        env.new_string(format!("Rust 1.88.0 · Rime {} · Lua protocol 1", runtime.version)).map(JString::into_raw).map_err(|_| "jni-allocation-failed".into())
    }).unwrap_or(std::ptr::null_mut())
}

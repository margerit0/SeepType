fn main() {
    println!("cargo:rerun-if-env-changed=STUDY_RIME_LIB_DIR");
    let directory = std::env::var("STUDY_RIME_LIB_DIR").expect("Build Android Rime first and set STUDY_RIME_LIB_DIR");
    println!("cargo:rustc-link-search=native={directory}");
    println!("cargo:rustc-link-lib=dylib=study_rime");
    println!("cargo:rerun-if-changed=../../android/native/bridge.h");
}

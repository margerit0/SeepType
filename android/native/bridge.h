// SPDX-License-Identifier: GPL-3.0-or-later
// Fixed, reviewed C ABI. Rime's extensible function table stays in C++.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  const char* text;
  const char* english;
} StudyCandidate;

typedef struct {
  const char* input;
  const char* preedit;
  size_t caret;
  int32_t preedit_cursor;
  int32_t page;
  int32_t page_size;
  int32_t highlighted;
  int32_t last_page;
  size_t candidate_count;
  const StudyCandidate* candidates;
} StudyRimeView;

int study_rime_initialize(const char* shared, const char* user, const char* build);
void study_rime_finalize(void);
int study_rime_export_word_frequency(const char* path);
int study_rime_import_word_frequency(const char* path);
uintptr_t study_rime_session(void);
void study_rime_destroy_session(uintptr_t session);
int study_rime_key(uintptr_t session, int code, int modifiers);
int study_rime_select(uintptr_t session, size_t index);
int study_rime_highlight(uintptr_t session, size_t index, int absolute);
int study_rime_forget(uintptr_t session, size_t index);
int study_rime_page(uintptr_t session, int backwards);
int study_rime_schema(uintptr_t session, const char* schema);
int study_rime_option(uintptr_t session, const char* key, int value);
int study_rime_property(uintptr_t session, const char* key, const char* value);
int study_rime_clear(uintptr_t session);
int study_rime_caret(uintptr_t session, size_t caret);
const StudyRimeView* study_rime_read(uintptr_t session);
void study_rime_free_view(const StudyRimeView* view);
char* study_rime_take_commit(uintptr_t session);
char* study_rime_get_property(uintptr_t session, const char* key);
void study_rime_free_text(char* text);
const char* study_rime_error(void);
const char* study_rime_version(void);

#ifdef __cplusplus
}
#endif

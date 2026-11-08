#pragma once

#include <cstdint>

namespace study {
// Called on the serialized service event path. Scheme changes are allowed only
// at session creation or before a new key-down; a live composition is retained.
void RefreshProductPreferences(void* api, std::uintptr_t session,
                               bool allowSchemaChange, bool newSession = false);
}

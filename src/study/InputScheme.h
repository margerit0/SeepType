#pragma once

#include <string_view>

namespace study {

enum class InputScheme { FullPinyin, NaturalDoublePinyin, Flypy };

inline const char* InputSchemaId(InputScheme scheme) {
  switch (scheme) {
    case InputScheme::NaturalDoublePinyin: return "study_double_pinyin";
    case InputScheme::Flypy: return "study_flypy";
    default: return "study";
  }
}

inline InputScheme ParseInputScheme(std::string_view id) {
  if (id == "study_double_pinyin") return InputScheme::NaturalDoublePinyin;
  if (id == "study_flypy") return InputScheme::Flypy;
  return InputScheme::FullPinyin;
}

}  // namespace study

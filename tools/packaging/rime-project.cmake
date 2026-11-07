# Called after each upstream project() has initialized MSVC. CMake's Windows
# ACP decoding must not garble the UTF-8 prefix produced with /utf-8.
if(MSVC AND DEFINED STUDY_MSVC_INCLUDE_PREFIX)
  set(CMAKE_CL_SHOWINCLUDES_PREFIX "${STUDY_MSVC_INCLUDE_PREFIX}")
endif()
